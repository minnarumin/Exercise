# -*- coding: utf-8 -*-
"""
4カメラ版 ガラス基板ノッチ判定ツール（単独動作版）
- 共通PLCトリガで4台のカメラを同時撮像・解析
- カメラごとに解析パラメータを設定可能
- 判定結果RU/RD/DONE/ERRはカメラごとに別デバイスへ書込み
"""

import os
import csv
import json
import time
import threading
import tempfile
import cv2
import numpy as np
import re
import logging
from collections import deque

LOGGER = logging.getLogger("notch_app_4cam")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)

# ====== オプション依存（存在チェック） ======
try:
    from pypylon import pylon
    HAS_PYLYON = True
except Exception:
    HAS_PYLYON = False

try:
    import pymcprotocol
    HAS_PYMC = True
except Exception:
    HAS_PYMC = False
from datetime import datetime
from dataclasses import dataclass, asdict, field

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

def imread_unicode(filename):
    data = np.fromfile(filename, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)

def _fit_line_L2(points_xy):
    pts = points_xy.astype(np.float32).reshape(-1,1,2)
    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
    return float(vx.ravel()[0]), float(vy.ravel()[0]), float(x0.ravel()[0]), float(y0.ravel()[0])

def _line_params_abc(vx, vy, x0, y0):
    a, b = vy, -vx
    c = -(a*x0 + b*y0)
    s = np.hypot(a, b)
    if s == 0: return 0.0, 0.0, 0.0
    return a/s, b/s, c/s

def _line_angle_deg(vx, vy):
    return float(np.degrees(np.arctan2(vy, vx)))

def _line_intersection(a1,b1,c1, a2,b2,c2):
    d = a1*b2 - a2*b1
    if abs(d) < 1e-9: return None
    x = (b1*c2 - b2*c1)/d
    y = (c1*a2 - c2*a1)/d
    return np.array([x,y], np.float32)

def _line_endpoints(a, b, c, width, height):
    pts=[]
    if abs(b)>1e-9:
        for X in (0, width-1):
            Y=int(round(-(a*X+c)/b)); pts.append((X,Y))
    if abs(a)>1e-9:
        for Y in (0, height-1):
            X=int(round(-(b*Y+c)/a)); pts.append((X,Y))
    pts_in=[p for p in pts if 0<=p[0]<width and 0<=p[1]<height]
    if len(pts_in)>=2:
        return pts_in[0], pts_in[1]
    return None, None

def _unit(v):
    n = np.linalg.norm(v)
    return v/n if n>1e-9 else v

def _clip_polygon_to_image(poly_pts, w, h):
    def intersection(A,B,edge):
        Ax,Ay = A; Bx,By = B
        if edge is left:
            t=(0-Ax)/(Bx-Ax+1e-12); return np.array([0, Ay+t*(By-Ay)], np.float32)
        if edge is right:
            t=((w-1)-Ax)/(Bx-Ax+1e-12); return np.array([w-1, Ay+t*(By-Ay)], np.float32)
        if edge is top:
            t=(0-Ay)/(By-Ay+1e-12); return np.array([Ax+t*(Bx-Ax), 0], np.float32)
        if edge is bottom:
            t=((h-1)-Ay)/(By-Ay+1e-12); return np.array([Ax+t*(Bx-Ax), h-1], np.float32)

    def clip_edge(points, edge):
        res=[]
        for i in range(len(points)):
            A=points[i]; B=points[(i+1)%len(points)]
            Ain=edge(A); Bin=edge(B)
            if Ain and Bin: res.append(B)
            elif Ain and not Bin: res.append(intersection(A,B,edge))
            elif (not Ain) and Bin: res.append(intersection(A,B,edge)); res.append(B)
        return res

    left   = lambda P: P[0] >= 0
    right  = lambda P: P[0] <= w-1
    top    = lambda P: P[1] >= 0
    bottom = lambda P: P[1] <= h-1

    pts=[p.astype(np.float32) for p in poly_pts]
    for edge in (left,right,top,bottom):
        if not pts: break
        pts = clip_edge(pts, edge)
    return np.array(pts, np.float32) if len(pts)>=3 else np.empty((0,2), np.float32)

def _extract_edge_points(mask_real, band, side, exclude_x_px, exclude_y_px, bbox):
    edges=cv2.Canny(mask_real, 50, 150)
    y_idx, x_idx = np.where(edges>0)
    x, y = x_idx.astype(np.int32), y_idx.astype(np.int32)
    x0, y0, bw, bh = bbox
    x1 = x0 + bw - 1; y1 = y0 + bh - 1
    if side=='top':
        y_min=max(0,y0); y_max=max(0,min(y1, y0+band))
        sel=(y>=y_min)&(y<=y_max)
        sel&=(x>=x0+int(exclude_x_px))&(x<=x1-int(exclude_x_px))
    elif side=='right':
        x_min=max(0, x1-band)
        sel=(x>=x_min)&(x<=x1)
        sel&=(y>=y0+int(exclude_y_px))&(y<=y1-int(exclude_y_px))
    elif side=='bottom':
        y_min=max(0, y1-band)
        sel=(y>=y_min)&(y<=y1)
        sel&=(x>=x0+int(exclude_x_px))&(x<=x1-int(exclude_x_px))
    else:
        raise ValueError("side must be 'top'|'right'|'bottom'")
    xs=x[sel].astype(np.float32); ys=y[sel].astype(np.float32)
    if xs.size<50: return np.empty((0,2), np.float32)
    return np.stack([xs,ys], axis=1)

def _make_corner_quad_from_lines(top_abc, right_abc, trim_x_px, trim_y_px, img_shape):
    a1,b1,c1=top_abc; a2,b2,c2=right_abc
    P=_line_intersection(a1,b1,c1, a2,b2,c2)
    if P is None: return np.empty((0,2), np.float32)
    t_top=_unit(np.array([-b1,a1],np.float32))
    t_right=_unit(np.array([-b2,a2],np.float32))
    if t_top[0]>0: t_top=-t_top
    if t_right[1]<0: t_right=-t_right
    p0=P; p1=P+t_right*trim_y_px; p2=p1+t_top*trim_x_px; p3=P+t_top*trim_x_px
    quad=np.array([p0,p1,p2,p3],np.float32)
    h,w=img_shape[:2]
    return _clip_polygon_to_image(quad, w, h)

def _make_corner_rd(right_abc, bottom_abc, trim_x_px, trim_y_px, img_shape):
    aR,bR,cR=right_abc; aB,bB,cB=bottom_abc
    P=_line_intersection(aR,bR,cR, aB,bB,cB)
    if P is None: return np.empty((0,2), np.float32)
    t_bottom=_unit(np.array([-bB,aB],np.float32))
    t_right =_unit(np.array([-bR,aR],np.float32))
    if t_bottom[0]>0: t_bottom=-t_bottom
    if t_right[1]>0:  t_right=-t_right
    p0=P; p1=P+t_right*trim_y_px; p2=p1+t_bottom*trim_x_px; p3=P+t_bottom*trim_x_px
    quad=np.array([p0,p1,p2,p3],np.float32)
    h,w=img_shape[:2]
    return _clip_polygon_to_image(quad, w, h)

def analyze_image(
    filepath,
    trim_ratio_x=0.25, trim_ratio_y=0.12, diff_thresh=15000,
    flip_horizontal=False,
    band_top=10, band_right=10, band_bottom=10,
    corner_exclude_x_px=200, corner_exclude_y_px=25
):
    img = imread_unicode(filepath)
    if img is None: raise RuntimeError(f"画像の読み込みに失敗: {filepath}")
    if flip_horizontal:
        img=cv2.flip(img, 1)
    gray=cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur=cv2.GaussianBlur(gray,(5,5),0)
    _,bin_img=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    bin_inv = 255 - bin_img
    contours,_=cv2.findContours(bin_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: raise RuntimeError(f"輪郭が検出できません: {filepath}")
    main_cnt=max(contours, key=cv2.contourArea)
    mask_real=np.zeros_like(bin_inv); cv2.drawContours(mask_real,[main_cnt],0,255,-1)

    rx=np.clip(float(trim_ratio_x),0.0,0.95); ry=np.clip(float(trim_ratio_y),0.0,0.95)
    x0,y0,bw,bh=cv2.boundingRect(main_cnt)

    pts_top   = _extract_edge_points(mask_real, band_top,   'top',    corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
    pts_bottom= _extract_edge_points(mask_real, band_bottom,'bottom', corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
    pts_side = _extract_edge_points(mask_real, band_right, 'right', corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
    if min(pts_top.shape[0], pts_side.shape[0], pts_bottom.shape[0]) < 50:
        raise RuntimeError("線抽出点が不足しています。band_* や exclude_*、trim比を見直してください。")

    vx,vy,xz,yz=_fit_line_L2(pts_top)
    a_top,b_top,c_top=_line_params_abc(vx,vy,xz,yz)
    top_angle_deg=_line_angle_deg(vx,vy)
    top_slope=vy/vx if abs(vx)>1e-9 else float("inf")
    vx,vy,xz,yz=_fit_line_L2(pts_side)
    a_side,b_side,c_side=_line_params_abc(vx,vy,xz,yz)
    side_angle_deg=_line_angle_deg(vx,vy)
    side_slope=vy/vx if abs(vx)>1e-9 else float("inf")
    vx,vy,xz,yz=_fit_line_L2(pts_bottom)
    a_bottom,b_bottom,c_bottom=_line_params_abc(vx,vy,xz,yz)
    bottom_angle_deg=_line_angle_deg(vx,vy)
    bottom_slope=vy/vx if abs(vx)>1e-9 else float("inf")

    trim_x_px=rx*bw; trim_y_px=ry*bh
    quad_up=_make_corner_quad_from_lines((a_top,b_top,c_top),(a_side,b_side,c_side), trim_x_px,trim_y_px,img.shape)
    quad_down=_make_corner_rd((a_side,b_side,c_side),(a_bottom,b_bottom,c_bottom), trim_x_px,trim_y_px,img.shape)

    mask_rect=np.zeros_like(bin_inv)
    if quad_up.shape[0]>=3: cv2.fillPoly(mask_rect,[quad_up.astype(np.int32)],255)
    if quad_down.shape[0]>=3: cv2.fillPoly(mask_rect,[quad_down.astype(np.int32)],255)
    mask_diff=cv2.subtract(mask_rect, mask_real)

    def _area_quad(mask, quad):
        if quad.shape[0]<3: return 0, np.zeros_like(mask)
        roi=np.zeros_like(mask); cv2.fillPoly(roi,[quad.astype(np.int32)],255)
        area=int(np.sum(cv2.bitwise_and(mask,roi)>128))
        return area, roi

    ru_area, ru_mask = _area_quad(mask_diff, quad_up)
    rd_area, rd_mask = _area_quad(mask_diff, quad_down)
    ru_result = "NOTCH" if ru_area>diff_thresh else "NO NOTCH"
    rd_result = "NOTCH" if rd_area>diff_thresh else "NO NOTCH"

    vis=img.copy()
    def _draw_line(img,a,b,c,color):
        hh,ww=img.shape[:2]; pts=[]
        if abs(b)>1e-9:
            for X in (0,ww-1):
                Y=int(round(-(a*X+c)/b)); pts.append((X,Y))
        if abs(a)>1e-9:
            for Y in (0,hh-1):
                X=int(round(-(b*Y+c)/a)); pts.append((X,Y))
        pts_in=[p for p in pts if 0<=p[0]<ww and 0<=p[1]<hh]
        if len(pts_in)>=2: cv2.line(img, pts_in[0], pts_in[1], color, 2, cv2.LINE_AA)

    hh, ww = img.shape[:2]
    top_p1, top_p2 = _line_endpoints(a_top, b_top, c_top, ww, hh)
    side_p1, side_p2 = _line_endpoints(a_side, b_side, c_side, ww, hh)
    bottom_p1, bottom_p2 = _line_endpoints(a_bottom, b_bottom, c_bottom, ww, hh)

    _draw_line(vis, a_top,b_top,c_top,         (0,255,0))
    _draw_line(vis, a_side,b_side,c_side,      (255,0,255))
    _draw_line(vis, a_bottom,b_bottom,c_bottom,(0,255,255))

    vis_mask=vis.copy()
    vis_mask[mask_diff>128]=[0,255,255]
    if quad_up.shape[0]>=3: cv2.polylines(vis_mask,[quad_up.astype(np.int32)],True,(0,0,255),3)
    if quad_down.shape[0]>=3: cv2.polylines(vis_mask,[quad_down.astype(np.int32)],True,(255,0,0),3)

    if quad_up.shape[0]>=3:
        P=np.mean(quad_up, axis=0).astype(int)
        cv2.putText(vis_mask, f"RU: {ru_result} ({ru_area})",(P[0]+5,P[1]+5),cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,0,255),3)
    if quad_down.shape[0]>=3:
        P=np.mean(quad_down, axis=0).astype(int)
        cv2.putText(vis_mask, f"RD: {rd_result} ({rd_area})",(P[0]+5,P[1]+5),cv2.FONT_HERSHEY_SIMPLEX,1.1,(255,0,0),3)

    if flip_horizontal:
        cv2.putText(vis_mask, "FLIP: ON", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3, cv2.LINE_AA)
        cv2.putText(vis_mask, "FLIP: ON", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30,30,30), 1, cv2.LINE_AA)

    side_label = "Side"
    return {
        "img_bgr": vis_mask,
        "ru_area": ru_area, "rd_area": rd_area,
        "ru_result": ru_result, "rd_result": rd_result,
        "mask_diff": mask_diff, "ru_roi_mask": ru_mask, "rd_roi_mask": rd_mask,
        "top_angle_deg": top_angle_deg, "side_angle_deg": side_angle_deg,
        "bottom_angle_deg": bottom_angle_deg, "top_slope": top_slope,
        "side_slope": side_slope, "bottom_slope": bottom_slope,
        "side_label": side_label,
        "top_line": (top_p1, top_p2),
        "side_line": (side_p1, side_p2),
        "bottom_line": (bottom_p1, bottom_p2)
    }


# ================== デバイス薄ラッパ ==================

def list_basler_devices():
    if not HAS_PYLYON:
        return []
    try:
        tlf = pylon.TlFactory.GetInstance()
        devs = tlf.EnumerateDevices()
        out = []
        for i, d in enumerate(devs):
            model = ""
            serial = ""
            try:
                model = d.GetModelName() or "Unknown"
            except Exception:
                model = "Unknown"
            try:
                serial = d.GetSerialNumber() or ""
            except Exception:
                serial = ""
            label = f"{i}: {model}" + (f" (S/N:{serial})" if serial else "")
            out.append((i, label))
        return out
    except Exception:
        return []

class BaslerCamera:
    def __init__(self, device_index=0, timeout_ms=3000, idle_reopen_sec=900, use_sw_trigger=True):
        self.device_index=device_index
        self.timeout_ms=timeout_ms
        self.idle_reopen_sec=max(0, int(idle_reopen_sec))
        self.use_sw_trigger=bool(use_sw_trigger)
        self.cam=None; self.converter=None
        self.last_snap_monotonic=0.0

    def open(self):
        if not HAS_PYLYON: raise RuntimeError("pypylon 未導入")
        tlf=pylon.TlFactory.GetInstance()
        devs=tlf.EnumerateDevices()
        if not devs: raise RuntimeError("Basler カメラが見つかりません")
        idx=min(max(0,self.device_index), len(devs)-1)
        self.cam=pylon.InstantCamera(tlf.CreateDevice(devs[idx]))
        self.cam.Open()
        self.converter=pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat=pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment=pylon.OutputBitAlignment_MsbAligned
        try:
            self.cam.ExposureAuto.SetValue("Off")
            self.cam.GainAuto.SetValue("Off")
        except Exception:
            pass
        self._configure_trigger_mode()
        self._start_grabbing_if_needed()

    def _configure_trigger_mode(self):
        try:
            self.cam.TriggerSelector.SetValue("FrameStart")
            if self.use_sw_trigger:
                self.cam.TriggerMode.SetValue("On")
                self.cam.TriggerSource.SetValue("Software")
            else:
                self.cam.TriggerMode.SetValue("Off")
        except Exception as e:
            LOGGER.warning("Failed to configure trigger mode (sw=%s): %s", self.use_sw_trigger, e)

    def _start_grabbing_if_needed(self):
        if self.cam and (not self.cam.IsGrabbing()):
            self.cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    def is_open(self):
        return bool(self.cam and self.cam.IsOpen())

    def is_healthy(self):
        return self.is_open()

    def reopen(self):
        self.close()
        self.open()

    def close(self):
        try:
            if self.cam:
                if self.cam.IsGrabbing(): self.cam.StopGrabbing()
                if self.cam.IsOpen(): self.cam.Close()
        except Exception:
            pass
        self.cam=None
        self.converter=None

    def _reopen_if_idle(self):
        if self.idle_reopen_sec <= 0:
            return
        now=time.monotonic()
        if self.last_snap_monotonic > 0 and (now - self.last_snap_monotonic) >= float(self.idle_reopen_sec):
            LOGGER.info("Camera idle for %.1fs, reopen before next snap", (now - self.last_snap_monotonic))
            self.reopen()

    def snap_bgr(self):
        self._reopen_if_idle()
        last_err=None
        for attempt in range(2):
            if not self.is_open():
                self.open()
            self._start_grabbing_if_needed()
            res=None
            try:
                if self.use_sw_trigger:
                    try:
                        self.cam.TriggerSoftware.Execute()
                    except Exception as e:
                        raise RuntimeError(f"ソフトウェアトリガ実行に失敗: {e}")
                res=self.cam.RetrieveResult(self.timeout_ms, pylon.TimeoutHandling_Return)
                if res is None or not res.GrabSucceeded():
                    raise RuntimeError("画像取得に失敗")
                image=self.converter.Convert(res)
                img=image.GetArray()
                self.last_snap_monotonic=time.monotonic()
                return img
            except Exception as e:
                last_err=e
                LOGGER.warning("Camera snap attempt %d failed: %s", attempt + 1, e)
                if attempt == 0:
                    try:
                        self.reopen()
                    except Exception as re:
                        LOGGER.warning("Camera reopen after snap failure failed: %s", re)
                        self.cam=None
                else:
                    break
            finally:
                try:
                    if res is not None:
                        res.Release()
                except Exception:
                    pass
        msg = str(last_err) if last_err is not None else "画像取得に失敗"
        if msg.startswith("画像取得に失敗"):
            raise RuntimeError(msg)
        raise RuntimeError(f"画像取得に失敗: {msg}")

    def __del__(self):
        self.close()

class PLCClient:
    def __init__(self):
        self.cli=None

    @staticmethod
    def _coerce_numeric(value):
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            return int(value)
        text = str(value).strip()
        if not text:
            raise ValueError("empty PLC value")
        return int(float(text))

    @staticmethod
    def _parse_d_bit_device(device: str):
        text = (device or "").strip()
        m = re.fullmatch(r'([Dd]\d+)\.(\d+)', text)
        if not m:
            return None
        word_dev = m.group(1).upper()
        bit_index = int(m.group(2))
        if not (0 <= bit_index <= 15):
            raise ValueError(f"Dデバイスのビット番号は0..15で指定してください: {device}")
        return word_dev, bit_index

    def connect(self, host:str, port:int):
        if not HAS_PYMC: raise RuntimeError("pymcprotocol 未導入")
        self.cli=pymcprotocol.Type3E(plctype="Q")
        self.cli.connect(host, port)

    def close(self):
        try:
            if self.cli: self.cli.close()
        except Exception:
            pass
        self.cli=None

    def read_bit(self, head:str)->bool:
        d_bit = self._parse_d_bit_device(head)
        if d_bit is not None:
            word_dev, bit_index = d_bit
            vals=self.cli.batchread_wordunits(headdevice=word_dev, readsize=1)
            raw = vals[0] if isinstance(vals,(list,tuple)) else vals
            w = self._coerce_numeric(raw) & 0xFFFF
            return bool((w >> bit_index) & 0x1)
        vals=self.cli.batchread_bitunits(headdevice=head, readsize=1)
        raw = vals[0] if isinstance(vals,(list,tuple)) else vals
        v=self._coerce_numeric(raw)
        return bool(v)

    def write_bit(self, head:str, value:bool):
        d_bit = self._parse_d_bit_device(head)
        if d_bit is not None:
            word_dev, bit_index = d_bit
            vals=self.cli.batchread_wordunits(headdevice=word_dev, readsize=1)
            raw = vals[0] if isinstance(vals,(list,tuple)) else vals
            w = self._coerce_numeric(raw) & 0xFFFF
            mask = 1 << bit_index
            w2 = (w | mask) if bool(value) else (w & (~mask & 0xFFFF))
            self.cli.batchwrite_wordunits(headdevice=word_dev, values=[w2])
            return
        self.cli.batchwrite_bitunits(headdevice=head, values=[1 if value else 0])

    def pulse_bit(self, head:str, ms:int=50):
        self.write_bit(head, True)
        time.sleep(max(0,ms)/1000.0)
        self.write_bit(head, False)

    def read_word(self, head:str)->int:
        vals=self.cli.batchread_wordunits(headdevice=head, readsize=1)
        raw = vals[0] if isinstance(vals,(list,tuple)) else vals
        v=self._coerce_numeric(raw)
        return v & 0xFFFF

    def write_word(self, head:str, value:int):
        self.cli.batchwrite_wordunits(headdevice=head, values=[int(value)&0xFFFF])


CONFIG_PATH_4CAM = os.path.join(os.path.expanduser("~"), ".notch_app_4cam_config.json")


@dataclass
class CameraParam:
    camera_index: int = 0
    flip_horizontal: bool = False
    trim_ratio_x: float = 0.25
    trim_ratio_y: float = 0.12
    diff_thresh: int = 15000
    band_top: int = 10
    band_right: int = 10
    band_bottom: int = 10
    corner_exclude_x_px: int = 200
    corner_exclude_y_px: int = 25

    dev_ru: str = "M101"
    dev_rd: str = "M102"
    dev_done: str = "M111"
    dev_err_to: str = "M121"
    dev_err_an: str = "M131"
    csv_filename: str = "result_cam1.csv"




def _default_cams():
    return [
        CameraParam(camera_index=0, dev_ru="M101", dev_rd="M102", dev_done="M111", dev_err_to="M121", dev_err_an="M131", csv_filename="result_cam1.csv"),
        CameraParam(camera_index=1, dev_ru="M103", dev_rd="M104", dev_done="M112", dev_err_to="M122", dev_err_an="M132", csv_filename="result_cam2.csv"),
        CameraParam(camera_index=2, dev_ru="M105", dev_rd="M106", dev_done="M113", dev_err_to="M123", dev_err_an="M133", csv_filename="result_cam3.csv"),
        CameraParam(camera_index=3, dev_ru="M107", dev_rd="M108", dev_done="M114", dev_err_to="M124", dev_err_an="M134", csv_filename="result_cam4.csv"),
    ]

@dataclass
class AppConfig4Cam:
    plc_ip: str = "192.168.1.2"
    plc_port: int = 1026
    dev_trig: str = "M100"
    dev_done: str = "M103"
    dev_busy: str = "M104"
    dev_err_to: str = "M105"
    dev_err_an: str = "M106"
    done_ms: int = 50
    timeout_ms: int = 3000
    use_sw_trig: bool = True

    output_dir: str = ""
    plc_shot_dir: str = ""
    auto_reconnect: bool = True

    cams: list[CameraParam] = field(default_factory=_default_cams)

    @staticmethod
    def load():
        try:
            with open(CONFIG_PATH_4CAM, "r", encoding="utf-8") as f:
                data = json.load(f)
            base = _default_cams()
            cams = []
            for i, x in enumerate(data.get("cams", [])):
                b = asdict(base[i]) if i < len(base) else asdict(CameraParam())
                b.update(x)
                cams.append(CameraParam(**b))
            if len(cams) < 4:
                cams.extend(base[len(cams):4])
            data["cams"] = cams[:4]
            return AppConfig4Cam(**{k: v for k, v in data.items() if k != "cams"}, cams=data["cams"])
        except Exception:
            return AppConfig4Cam()

    def save(self):
        try:
            payload = asdict(self)
            with open(CONFIG_PATH_4CAM, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class NotchApp4Cam(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("4カメラ版 ノッチ判定ツール")
        self.geometry("1280x880")

        self.cfg = AppConfig4Cam.load()
        self._trace_lock = False

        self.plc = PLCClient()
        self.plc_connected = False
        self.plc_thread = None
        self.plc_stop = False
        self.prev_trig = False
        self._plc_lock = threading.RLock()
        self._csv_lock = threading.RLock()

        self.cameras = [None, None, None, None]
        self._cam_locks = [threading.RLock() for _ in range(4)]
        self.cam_panels = []
        self.cam_grab_stop = [threading.Event() for _ in range(4)]
        self.cam_grab_threads = [None, None, None, None]
        self.cam_select_vars = []
        self.camera_candidates = []
        self.camera_label_to_index = {}
        self._analysis_lines = deque(maxlen=5)

        self.var_plc_ip = tk.StringVar(value=self.cfg.plc_ip)
        self.var_plc_port = tk.IntVar(value=self.cfg.plc_port)
        self.var_dev_trig = tk.StringVar(value=self.cfg.dev_trig)
        self.var_dev_done = tk.StringVar(value=self.cfg.dev_done)
        self.var_dev_busy = tk.StringVar(value=self.cfg.dev_busy)
        self.var_dev_err_to = tk.StringVar(value=self.cfg.dev_err_to)
        self.var_dev_err_an = tk.StringVar(value=self.cfg.dev_err_an)
        self.var_done_ms = tk.IntVar(value=self.cfg.done_ms)
        self.var_timeout_ms = tk.IntVar(value=self.cfg.timeout_ms)
        self.var_use_sw_trig = tk.BooleanVar(value=self.cfg.use_sw_trig)
        self.var_output_dir = tk.StringVar(value=self.cfg.output_dir)
        self.var_plc_shot_dir = tk.StringVar(value=self.cfg.plc_shot_dir)
        self.var_auto_reconnect = tk.BooleanVar(value=self.cfg.auto_reconnect)

        self.cam_vars = []
        for c in self.cfg.cams:
            self.cam_vars.append({
                "camera_index": tk.IntVar(value=c.camera_index),
                "flip_horizontal": tk.BooleanVar(value=c.flip_horizontal),
                "trim_ratio_x": tk.DoubleVar(value=c.trim_ratio_x),
                "trim_ratio_y": tk.DoubleVar(value=c.trim_ratio_y),
                "diff_thresh": tk.IntVar(value=c.diff_thresh),
                "band_top": tk.IntVar(value=c.band_top),
                "band_right": tk.IntVar(value=c.band_right),
                "band_bottom": tk.IntVar(value=c.band_bottom),
                "corner_exclude_x_px": tk.IntVar(value=c.corner_exclude_x_px),
                "corner_exclude_y_px": tk.IntVar(value=c.corner_exclude_y_px),
                "dev_ru": tk.StringVar(value=c.dev_ru),
                "dev_rd": tk.StringVar(value=c.dev_rd),
                "dev_done": tk.StringVar(value=c.dev_done),
                "dev_err_to": tk.StringVar(value=c.dev_err_to),
                "dev_err_an": tk.StringVar(value=c.dev_err_an),
                "csv_filename": tk.StringVar(value=c.csv_filename),
            })
            self.cam_select_vars.append(tk.StringVar(value=""))

        self._build_ui()
        self._bind_traces()
        self._post_status("起動完了")

    def _build_ui(self):
        self._build_menu()

        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        ops = ttk.Frame(root)
        ops.pack(fill="x", pady=(0, 4))
        ttk.Button(ops, text="PLC接続", command=self.on_plc_connect, bootstyle=SUCCESS).pack(side="left")
        ttk.Button(ops, text="PLC切断", command=self.on_plc_disconnect).pack(side="left", padx=4)
        ttk.Button(ops, text="監視開始", command=self.on_watch_start, bootstyle=PRIMARY).pack(side="left", padx=4)
        ttk.Button(ops, text="監視停止", command=self.on_watch_stop).pack(side="left")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)
        for i, v in enumerate(self.cam_vars, start=1):
            frm = ttk.Frame(nb, padding=8)
            nb.add(frm, text=f"Cam{i}")
            self._build_cam_tab(frm, v, i - 1)

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(6, 0))

        status_box = ttk.Labelframe(bottom, text="ステータス", padding=4)
        status_box.pack(side="left", fill="both", expand=True)
        self.txt_status = tk.Text(status_box, height=8, wrap="word", state="disabled")
        self.txt_status.pack(fill="both", expand=True)

        analysis_box = ttk.Labelframe(bottom, text="解析結果(最新5件)", padding=4)
        analysis_box.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.txt_analysis = tk.Text(analysis_box, height=8, wrap="word", state="disabled")
        self.txt_analysis.pack(fill="both", expand=True)

        self._refresh_camera_candidates()

    def _build_menu(self):
        menubar = tk.Menu(self)

        menu_setting = tk.Menu(menubar, tearoff=0)
        menu_setting.add_command(label="PLC共通設定...", command=self._open_plc_common_settings)
        menu_setting.add_command(label="設定を保存", command=lambda: (self._sync_cfg(), self.cfg.save(), self._post_status("設定を保存しました")))
        menubar.add_cascade(label="設定", menu=menu_setting)

        menu_cam = tk.Menu(menubar, tearoff=0)
        menu_cam.add_command(label="カメラ別設定...", command=self._open_camera_settings)
        menu_cam.add_command(label="接続カメラ再検出", command=self._refresh_camera_candidates)
        menubar.add_cascade(label="カメラ", menu=menu_cam)

        self.config(menu=menubar)

    def _open_plc_common_settings(self):
        win = tk.Toplevel(self)
        win.title("PLC共通設定")
        win.geometry("980x360")
        win.transient(self)

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)

        r1 = ttk.Frame(frm); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="IP").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_plc_ip, width=16).pack(side="left", padx=4)
        ttk.Label(r1, text="Port").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_plc_port, width=8).pack(side="left", padx=4)
        ttk.Label(r1, text="Trig").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_dev_trig, width=10).pack(side="left", padx=4)

        r2 = ttk.Frame(frm); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="DONE").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_done, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="BUSY").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_busy, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="ERR_TO").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_err_to, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="ERR_AN").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_err_an, width=10).pack(side="left", padx=4)

        r3 = ttk.Frame(frm); r3.pack(fill="x", pady=2)
        ttk.Checkbutton(r3, text="SWトリガ", variable=self.var_use_sw_trig).pack(side="left")
        ttk.Label(r3, text="Timeout[ms]").pack(side="left", padx=(10, 2))
        ttk.Entry(r3, textvariable=self.var_timeout_ms, width=8).pack(side="left")
        ttk.Label(r3, text="DONE幅[ms]").pack(side="left", padx=(10, 2))
        ttk.Entry(r3, textvariable=self.var_done_ms, width=8).pack(side="left")
        ttk.Checkbutton(r3, text="自動再接続", variable=self.var_auto_reconnect).pack(side="left", padx=(12, 0))

        r4 = ttk.Frame(frm); r4.pack(fill="x", pady=2)
        ttk.Label(r4, text="出力先").pack(side="left")
        ttk.Entry(r4, textvariable=self.var_output_dir, width=45).pack(side="left", padx=4)
        ttk.Label(r4, text="PLC保存先").pack(side="left")
        ttk.Entry(r4, textvariable=self.var_plc_shot_dir, width=30).pack(side="left", padx=4)

        r5 = ttk.Frame(frm); r5.pack(fill="x", pady=(10, 0))
        ttk.Button(r5, text="保存して閉じる", bootstyle=PRIMARY, command=lambda: (self._sync_cfg(), self.cfg.save(), win.destroy())).pack(side="right")

    def _open_camera_settings(self):
        self._refresh_camera_candidates()
        win = tk.Toplevel(self)
        win.title("カメラ別設定")
        win.geometry("920x420")
        win.transient(self)

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)

        nb = ttk.Notebook(frm)
        nb.pack(fill="both", expand=True)

        labels = [label for _, label in self.camera_candidates]
        for i in range(4):
            tab = ttk.Frame(nb, padding=8)
            nb.add(tab, text=f"Cam{i+1}")

            r1 = ttk.Frame(tab); r1.pack(fill="x", pady=2)
            ttk.Label(r1, text="カメラ選択").pack(side="left")
            cmb = ttk.Combobox(r1, textvariable=self.cam_select_vars[i], state="readonly", width=36, values=labels)
            cmb.pack(side="left", padx=4)
            cmb.bind("<<ComboboxSelected>>", lambda _e, x=i: self._on_cam_device_selected(x))

            v = self.cam_vars[i]
            r2 = ttk.Frame(tab); r2.pack(fill="x", pady=2)
            ttk.Label(r2, text="結果RU").pack(side="left")
            ttk.Entry(r2, textvariable=v["dev_ru"], width=10).pack(side="left", padx=4)
            ttk.Label(r2, text="結果RD").pack(side="left")
            ttk.Entry(r2, textvariable=v["dev_rd"], width=10).pack(side="left", padx=4)
            ttk.Label(r2, text="DONE").pack(side="left")
            ttk.Entry(r2, textvariable=v["dev_done"], width=10).pack(side="left", padx=4)

            r3 = ttk.Frame(tab); r3.pack(fill="x", pady=2)
            ttk.Label(r3, text="ERR_TO").pack(side="left")
            ttk.Entry(r3, textvariable=v["dev_err_to"], width=10).pack(side="left", padx=4)
            ttk.Label(r3, text="ERR_AN").pack(side="left")
            ttk.Entry(r3, textvariable=v["dev_err_an"], width=10).pack(side="left", padx=4)
            ttk.Label(r3, text="CSV").pack(side="left")
            ttk.Entry(r3, textvariable=v["csv_filename"], width=28).pack(side="left", padx=4)

        rbtn = ttk.Frame(frm)
        rbtn.pack(fill="x", pady=(8, 0))
        ttk.Button(rbtn, text="再検出", command=self._refresh_camera_candidates).pack(side="left")
        ttk.Button(rbtn, text="保存して閉じる", bootstyle=PRIMARY,
                   command=lambda: (self._sync_cfg(), self.cfg.save(), win.destroy())).pack(side="right")

    def _refresh_camera_candidates(self):
        cands = list_basler_devices()
        if not cands:
            cands = [(i, f"{i}: Camera{i+1}(未検出)") for i in range(4)]
            self._post_status("接続カメラ検出: 0台（未検出表示で代替）")
        else:
            self._post_status(f"接続カメラ検出: {len(cands)}台")
        self.camera_candidates = cands
        self.camera_label_to_index = {label: idx for idx, label in cands}
        labels = [label for _, label in cands]

        for i in range(min(4, len(self.cam_select_vars))):
            idx = int(self.cam_vars[i]["camera_index"].get())
            match = next((lab for n, lab in cands if n == idx), None)
            if match is None:
                match = labels[min(max(idx, 0), len(labels)-1)]
                self.cam_vars[i]["camera_index"].set(self.camera_label_to_index.get(match, 0))
            self.cam_select_vars[i].set(match)

    def _on_cam_device_selected(self, cam_idx):
        label = self.cam_select_vars[cam_idx].get()
        idx = self.camera_label_to_index.get(label)
        if idx is None:
            return
        self.cam_vars[cam_idx]["camera_index"].set(int(idx))

    def _build_cam_tab(self, parent, v, cam_idx):
        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)

        ctrl = ttk.Labelframe(body, text="画像処理パラメータ", padding=8, width=420)
        ctrl.pack(side="left", fill="y", expand=False, padx=(0, 6))
        ctrl.pack_propagate(False)

        r1 = ttk.Frame(ctrl); r1.pack(fill="x", pady=2)
        ttk.Checkbutton(r1, text="左右反転", variable=v["flip_horizontal"]).pack(side="left", padx=10)

        r2 = ttk.Frame(ctrl); r2.pack(fill="x", pady=2)
        for key, label, w in [
            ("trim_ratio_x", "trim_x", 6), ("trim_ratio_y", "trim_y", 6), ("diff_thresh", "th", 8),
            ("band_top", "band_top", 6), ("band_right", "band_right", 6), ("band_bottom", "band_bottom", 6),
            ("corner_exclude_x_px", "ex_x", 6), ("corner_exclude_y_px", "ex_y", 6)
        ]:
            ttk.Label(r2, text=label).pack(side="left")
            ttk.Entry(r2, textvariable=v[key], width=w).pack(side="left", padx=2)

        r5 = ttk.Frame(ctrl); r5.pack(fill="x", pady=(8, 4))
        ttk.Button(r5, text="撮像", bootstyle=PRIMARY, command=lambda i=cam_idx: self.on_cam_snap(i)).pack(side="left")
        ttk.Button(r5, text="連続Grab開始", bootstyle=SUCCESS, command=lambda i=cam_idx: self.on_cam_grab_start(i)).pack(side="left", padx=4)
        ttk.Button(r5, text="連続Grab停止", bootstyle=WARNING, command=lambda i=cam_idx: self.on_cam_grab_stop(i)).pack(side="left")

        preview = ttk.Labelframe(body, text="プレビュー", padding=6)
        preview.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(preview, width=640, height=360, bg="#111111", highlightthickness=1, highlightbackground="#444444")
        canvas.pack(fill="both", expand=True)
        result_var = tk.StringVar(value="未撮像")
        ttk.Label(preview, textvariable=result_var, justify="left", anchor="w").pack(fill="x", pady=(4, 0))

        self.cam_panels.append({"canvas": canvas, "result_var": result_var, "photo": None})

    def _analyze_bgr_for_cam(self, cam_idx, bgr):
        tmp_dir = self.cfg.plc_shot_dir or tempfile.gettempdir()
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"_preview_cam{cam_idx+1}_{time.time_ns()}.png")
        ok, buf = cv2.imencode('.png', bgr)
        if not ok:
            raise RuntimeError("画像エンコード失敗")
        buf.tofile(tmp_path)
        try:
            c = self.cfg.cams[cam_idx]
            return analyze_image(
                tmp_path,
                trim_ratio_x=c.trim_ratio_x,
                trim_ratio_y=c.trim_ratio_y,
                diff_thresh=c.diff_thresh,
                flip_horizontal=c.flip_horizontal,
                band_top=c.band_top,
                band_right=c.band_right,
                band_bottom=c.band_bottom,
                corner_exclude_x_px=c.corner_exclude_x_px,
                corner_exclude_y_px=c.corner_exclude_y_px,
            )
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _post_cam_preview(self, cam_idx, img_bgr, result_text):
        def _update():
            if cam_idx >= len(self.cam_panels):
                return
            panel = self.cam_panels[cam_idx]
            canvas = panel["canvas"]
            cw = max(int(canvas.winfo_width()), 10)
            ch = max(int(canvas.winfo_height()), 10)
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            scale = min(cw / max(w, 1), ch / max(h, 1))
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            pil = Image.fromarray(rgb).resize((nw, nh), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(pil)
            canvas.delete("all")
            canvas.create_image(cw // 2, ch // 2, image=photo, anchor="center")
            panel["photo"] = photo
            panel["result_var"].set(result_text)
            line = f"{time.strftime('%H:%M:%S')} | Cam{cam_idx+1} | {result_text}"
            self._analysis_lines.appendleft(line)
            self.txt_analysis.configure(state="normal")
            self.txt_analysis.delete("1.0", "end")
            self.txt_analysis.insert("1.0", "\n".join(self._analysis_lines))
            self.txt_analysis.configure(state="disabled")

        self.after(0, _update)

    def _run_cam_snap_and_preview(self, cam_idx):
        bgr = self._cam_snap(cam_idx)
        try:
            res = self._analyze_bgr_for_cam(cam_idx, bgr)
            txt = (
                f"RU={res['ru_result']}({res['ru_area']}) / "
                f"RD={res['rd_result']}({res['rd_area']}) / "
                f"角度 Top={res['top_angle_deg']:.2f} Side={res['side_angle_deg']:.2f} Bottom={res['bottom_angle_deg']:.2f}"
            )
            self._post_cam_preview(cam_idx, res["img_bgr"], txt)
        except Exception as e:
            self._post_cam_preview(cam_idx, bgr, f"解析エラー: {e}")
            raise

    def on_cam_snap(self, cam_idx):
        try:
            self._sync_cfg()
            self._run_cam_snap_and_preview(cam_idx)
            self._post_status(f"Cam{cam_idx+1} 手動撮像完了")
        except Exception as e:
            self._post_status(f"Cam{cam_idx+1} 手動撮像エラー: {e}")

    def _cam_grab_loop(self, cam_idx):
        stop_event = self.cam_grab_stop[cam_idx]
        while not stop_event.is_set():
            try:
                self._run_cam_snap_and_preview(cam_idx)
            except Exception as e:
                self._post_status(f"Cam{cam_idx+1} 連続Grabエラー: {e}")
            stop_event.wait(0.2)

    def on_cam_grab_start(self, cam_idx):
        self._sync_cfg()
        t = self.cam_grab_threads[cam_idx]
        if t and t.is_alive():
            self._post_status(f"Cam{cam_idx+1} は既に連続Grab中")
            return
        self.cam_grab_stop[cam_idx].clear()
        th = threading.Thread(target=self._cam_grab_loop, args=(cam_idx,), daemon=True)
        self.cam_grab_threads[cam_idx] = th
        th.start()
        self._post_status(f"Cam{cam_idx+1} 連続Grab開始")

    def on_cam_grab_stop(self, cam_idx):
        self.cam_grab_stop[cam_idx].set()
        t = self.cam_grab_threads[cam_idx]
        if t and t.is_alive():
            t.join(timeout=1.0)
        self.cam_grab_threads[cam_idx] = None
        self._post_status(f"Cam{cam_idx+1} 連続Grab停止")

    def _bind_traces(self):
        def on_change(*_):
            if self._trace_lock:
                return
            self._sync_cfg()
            self.cfg.save()

        vars_all = [
            self.var_plc_ip, self.var_plc_port, self.var_dev_trig, self.var_dev_done,
            self.var_dev_busy, self.var_dev_err_to, self.var_dev_err_an,
            self.var_done_ms, self.var_timeout_ms, self.var_use_sw_trig,
            self.var_output_dir, self.var_plc_shot_dir, self.var_auto_reconnect,
        ]
        for v in self.cam_vars:
            vars_all.extend(v.values())
        for x in vars_all:
            x.trace_add("write", on_change)

    def _sync_cfg(self):
        self.cfg.plc_ip = self.var_plc_ip.get().strip()
        self.cfg.plc_port = int(self.var_plc_port.get())
        self.cfg.dev_trig = self.var_dev_trig.get().strip()
        self.cfg.dev_done = self.var_dev_done.get().strip()
        self.cfg.dev_busy = self.var_dev_busy.get().strip()
        self.cfg.dev_err_to = self.var_dev_err_to.get().strip()
        self.cfg.dev_err_an = self.var_dev_err_an.get().strip()
        self.cfg.done_ms = int(self.var_done_ms.get())
        self.cfg.timeout_ms = int(self.var_timeout_ms.get())
        self.cfg.use_sw_trig = bool(self.var_use_sw_trig.get())
        self.cfg.output_dir = self.var_output_dir.get().strip()
        self.cfg.plc_shot_dir = self.var_plc_shot_dir.get().strip()
        self.cfg.auto_reconnect = bool(self.var_auto_reconnect.get())

        cams = []
        for v in self.cam_vars:
            cams.append(CameraParam(
                camera_index=int(v["camera_index"].get()),
                flip_horizontal=bool(v["flip_horizontal"].get()),
                trim_ratio_x=float(v["trim_ratio_x"].get()),
                trim_ratio_y=float(v["trim_ratio_y"].get()),
                diff_thresh=int(v["diff_thresh"].get()),
                band_top=int(v["band_top"].get()),
                band_right=int(v["band_right"].get()),
                band_bottom=int(v["band_bottom"].get()),
                corner_exclude_x_px=int(v["corner_exclude_x_px"].get()),
                corner_exclude_y_px=int(v["corner_exclude_y_px"].get()),
                dev_ru=v["dev_ru"].get().strip(),
                dev_rd=v["dev_rd"].get().strip(),
                dev_done=v["dev_done"].get().strip(),
                dev_err_to=v["dev_err_to"].get().strip(),
                dev_err_an=v["dev_err_an"].get().strip(),
                csv_filename=v["csv_filename"].get().strip() or "result.csv",
            ))
        self.cfg.cams = cams

    def _post_status(self, text):
        line = f"{time.strftime('%H:%M:%S')} | {text}"
        self.txt_status.configure(state="normal")
        self.txt_status.insert("1.0", line + "\n")
        self.txt_status.configure(state="disabled")

    def _append_cam_csv(self, cam_no, cam_cfg, row):
        base = self.cfg.output_dir or self.cfg.plc_shot_dir or tempfile.gettempdir()
        os.makedirs(base, exist_ok=True)
        filename = cam_cfg.csv_filename.strip() if cam_cfg.csv_filename else f"result_cam{cam_no+1}.csv"
        csv_path = os.path.join(base, filename)
        header = ["timestamp", "camera_no", "filename", "ru_result", "rd_result", "ru_area", "rd_area", "error"]
        with self._csv_lock:
            exists = os.path.isfile(csv_path)
            with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(header)
                w.writerow(row)

    def _cam_open_if_needed(self, idx):
        with self._cam_locks[idx]:
            cfg = self.cfg.cams[idx]
            if self.cameras[idx] is None:
                cam = BaslerCamera(
                    device_index=cfg.camera_index,
                    timeout_ms=self.cfg.timeout_ms,
                    use_sw_trigger=self.cfg.use_sw_trig,
                )
                cam.open()
                self.cameras[idx] = cam
            else:
                cam = self.cameras[idx]
                need = (cam.device_index != cfg.camera_index or
                        cam.timeout_ms != self.cfg.timeout_ms or
                        cam.use_sw_trigger != self.cfg.use_sw_trig or
                        (not cam.is_healthy()))
                if need:
                    cam.device_index = cfg.camera_index
                    cam.timeout_ms = self.cfg.timeout_ms
                    cam.use_sw_trigger = self.cfg.use_sw_trig
                    cam.reopen()
            return self.cameras[idx]

    def _cam_snap(self, idx):
        with self._cam_locks[idx]:
            cam = self._cam_open_if_needed(idx)
            return cam.snap_bgr()

    def on_plc_connect(self):
        try:
            with self._plc_lock:
                self.plc.connect(self.cfg.plc_ip, self.cfg.plc_port)
            self.plc_connected = True
            self._post_status("PLC接続OK")
        except Exception as e:
            self.plc_connected = False
            self._post_status(f"[PLC接続エラー] {e}")

    def on_plc_disconnect(self):
        self.on_watch_stop()
        try:
            with self._plc_lock:
                self.plc.close()
        except Exception:
            pass
        self.plc_connected = False
        self._post_status("PLC切断")

    def on_watch_start(self):
        if not self.plc_connected:
            self._post_status("PLC未接続")
            return
        self.plc_stop = False
        self.prev_trig = False
        if self.plc_thread and self.plc_thread.is_alive():
            self._post_status("既に監視中")
            return
        self.plc_thread = threading.Thread(target=self._plc_loop, daemon=True)
        self.plc_thread.start()
        self._post_status("監視開始")

    def on_watch_stop(self):
        self.plc_stop = True
        if self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.join(timeout=1.0)
        self.plc_thread = None
        self._post_status("監視停止")

    def _plc_loop(self):
        while not self.plc_stop:
            try:
                with self._plc_lock:
                    trig = self.plc.read_bit(self.cfg.dev_trig)
            except Exception as e:
                self._post_status(f"PLC読取エラー: {e}")
                time.sleep(0.2)
                continue

            if trig and not self.prev_trig:
                self._process_trigger()

            self.prev_trig = trig
            time.sleep(0.01)

    def _process_trigger(self):
        self._post_status("トリガ検出: 4カメラ処理開始")
        with self._plc_lock:
            self.plc.write_bit(self.cfg.dev_busy, True)
            self.plc.write_bit(self.cfg.dev_err_to, False)
            self.plc.write_bit(self.cfg.dev_err_an, False)

        captures = [{} for _ in range(4)]

        def _capture_worker(i):
            c = self.cfg.cams[i]
            try:
                bgr = self._cam_snap(i)
                shot_dir = self.cfg.plc_shot_dir or tempfile.gettempdir()
                os.makedirs(shot_dir, exist_ok=True)
                shot_path = os.path.join(shot_dir, f"PLCshot_cam{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png")
                ok, buf = cv2.imencode('.png', bgr)
                if not ok:
                    raise RuntimeError("画像エンコード失敗")
                buf.tofile(shot_path)
                captures[i] = {"ok": True, "path": shot_path}
            except Exception as e:
                captures[i] = {"ok": False, "err": str(e)}

        workers = [threading.Thread(target=_capture_worker, args=(i,), daemon=True) for i in range(4)]
        for t in workers:
            t.start()
        for t in workers:
            t.join()

        any_to_error = False
        any_an_error = False

        for i, c in enumerate(self.cfg.cams):
            ru = False
            rd = False
            to_error = False
            an_error = False
            ru_area = -1
            rd_area = -1
            shot_path = captures[i].get("path", "")
            err_msg = ""

            if captures[i].get("ok"):
                try:
                    res = analyze_image(
                        shot_path,
                        trim_ratio_x=c.trim_ratio_x,
                        trim_ratio_y=c.trim_ratio_y,
                        diff_thresh=c.diff_thresh,
                        flip_horizontal=c.flip_horizontal,
                        band_top=c.band_top,
                        band_right=c.band_right,
                        band_bottom=c.band_bottom,
                        corner_exclude_x_px=c.corner_exclude_x_px,
                        corner_exclude_y_px=c.corner_exclude_y_px,
                    )
                    ru = (res["ru_result"] == "NOTCH")
                    rd = (res["rd_result"] == "NOTCH")
                    ru_area = int(res["ru_area"])
                    rd_area = int(res["rd_area"])
                    preview_txt = (
                        f"RU={res['ru_result']}({res['ru_area']}) / "
                        f"RD={res['rd_result']}({res['rd_area']}) / "
                        f"角度 Top={res['top_angle_deg']:.2f} Side={res['side_angle_deg']:.2f} Bottom={res['bottom_angle_deg']:.2f}"
                    )
                    self._post_cam_preview(i, res["img_bgr"], preview_txt)
                except Exception as e:
                    an_error = True
                    err_msg = f"ANALYZE:{e}"
                    try:
                        raw = imread_unicode(shot_path) if shot_path else None
                        if raw is not None:
                            self._post_cam_preview(i, raw, f"解析エラー: {e}")
                    except Exception:
                        pass
                    self._post_status(f"Cam{i+1} 解析エラー: {e}")
            else:
                to_error = True
                err_msg = f"CAPTURE:{captures[i].get('err', '')}"
                self._post_status(f"Cam{i+1} 撮像エラー: {captures[i].get('err', '')}")

            try:
                with self._plc_lock:
                    self.plc.write_bit(c.dev_ru, ru)
                    self.plc.write_bit(c.dev_rd, rd)
                    self.plc.write_bit(c.dev_err_to, to_error)
                    self.plc.write_bit(c.dev_err_an, an_error)
                    self.plc.pulse_bit(c.dev_done, self.cfg.done_ms)
            except Exception as e:
                to_error = True
                err_msg = (err_msg + " | " if err_msg else "") + f"WRITE:{e}"
                self._post_status(f"Cam{i+1} PLC書込エラー: {e}")

            any_to_error = any_to_error or to_error
            any_an_error = any_an_error or an_error

            self._append_cam_csv(i, c, [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                i + 1,
                os.path.basename(shot_path) if shot_path else "",
                int(ru), int(rd), ru_area, rd_area, err_msg,
            ])

        with self._plc_lock:
            self.plc.write_bit(self.cfg.dev_err_to, any_to_error)
            self.plc.write_bit(self.cfg.dev_err_an, any_an_error)
            self.plc.write_bit(self.cfg.dev_busy, False)

        self._post_status(f"4カメラ返答完了 TO_ERR={int(any_to_error)} AN_ERR={int(any_an_error)}")

    def destroy(self):
        try:
            self.on_watch_stop()
            self.on_plc_disconnect()
            for i in range(4):
                self.on_cam_grab_stop(i)
            for i in range(4):
                try:
                    if self.cameras[i]:
                        self.cameras[i].close()
                except Exception:
                    pass
            self._sync_cfg()
            self.cfg.save()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    app = NotchApp4Cam()
    app.mainloop()
