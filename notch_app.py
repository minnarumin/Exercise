# -*- coding: utf-8 -*-
"""
ガラス基板ノッチ判定ツール（Basler撮像 + PLC返答 + 自動再接続 + 一時ファイル上限 + CSVローテーション + 連続Grab）
- 解析は直線近似のみ（RU/RD）
- すべての通知はステータス（最新5行固定）に集約（ダイアログ非使用）
- 設定は自動保存/復元（ユーザホーム: ~/.notch_app_config.json）
- 左ペインは全体スクロール & 左にマージン & 幅改善
- 起動時/断時の自動再接続→監視開始（手動停止/切断時は除外）
- PLC 連携のパラメータ入力 UI はメインから撤去（ボタンは残す）
- RU/RD/完了テストはメニューバー「操作」に移動（メイン画面から削除）
- 連続Grab（動画）開始/停止（手動時のみ）を追加
- PLCトリガ結果も result.csv に追記（エラーはエラーと記録）
- result.csv は最大レコード数を設定可。超過時は古い行から上書き（ローテーション）
- PLCトリガで保存する画像の保存先を設定可（空ならTemp）
- パラメータ変更時は200msデバウンス付きで自動プレビュー更新
"""

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
import csv, os, re, traceback, tempfile, time, json, glob, threading
from dataclasses import dataclass, asdict, field, fields
from collections import deque

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


# ================== 低レベルユーティリティ ==================
def imread_unicode(filename):
    data = np.fromfile(filename, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)

def save_to_csv(csv_path, row, header=None):
    d = os.path.dirname(csv_path)
    if d: os.makedirs(d, exist_ok=True)
    exists = os.path.isfile(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if (header is not None) and (not exists):
            w.writerow(header)
        w.writerow(row)

def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)

def save_result_image(img_bgr, src_filepath, out_dir):
    try:
        filename_only = os.path.basename(src_filepath)
        stem, _ = os.path.splitext(filename_only)
        stem = safe_filename(stem)
        save_dir = out_dir if out_dir else os.path.dirname(src_filepath) or tempfile.gettempdir()
        os.makedirs(save_dir, exist_ok=True)
        out_path = os.path.join(save_dir, stem + "_result.png")
        ok, buf = cv2.imencode(".png", img_bgr)
        if not ok: return None
        buf.tofile(out_path)
        return out_path if os.path.isfile(out_path) else None
    except Exception:
        return None

def list_basler_devices():
    if not HAS_PYLYON:
        return []
    try:
        tlf=pylon.TlFactory.GetInstance()
        devs=tlf.EnumerateDevices()
        results=[]
        for idx, dev in enumerate(devs):
            try:
                model=dev.GetModelName()
            except Exception:
                model="Unknown"
            try:
                serial=dev.GetSerialNumber()
            except Exception:
                serial=""
            label=f"{idx}: {model}" + (f" ({serial})" if serial else "")
            results.append((idx, label))
        return results
    except Exception:
        return []


# ================== 画像処理（直線近似のみ） ==================
def _fit_line_L2(points_xy):
    pts = points_xy.astype(np.float32).reshape(-1,1,2)
    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
    return float(vx), float(vy), float(x0), float(y0)

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
    elif side=='left':
        x_max=min(x1, x0+band)
        sel=(x>=x0)&(x<=x_max)
        sel&=(y>=y0+int(exclude_y_px))&(y<=y1-int(exclude_y_px))
    elif side=='right':
        x_min=max(0, x1-band)
        sel=(x>=x_min)&(x<=x1)
        sel&=(y>=y0+int(exclude_y_px))&(y<=y1-int(exclude_y_px))
    elif side=='bottom':
        y_min=max(0, y1-band)
        sel=(y>=y_min)&(y<=y1)
        sel&=(x>=x0+int(exclude_x_px))&(x<=x1-int(exclude_x_px))
    else:
        raise ValueError("side must be 'top'|'left'|'right'|'bottom'")
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

def _make_corner_lu(top_abc, left_abc, trim_x_px, trim_y_px, img_shape):
    a1,b1,c1=top_abc; a2,b2,c2=left_abc
    P=_line_intersection(a1,b1,c1, a2,b2,c2)
    if P is None: return np.empty((0,2), np.float32)
    t_top=_unit(np.array([-b1,a1],np.float32))
    t_left=_unit(np.array([-b2,a2],np.float32))
    if t_top[0]<0: t_top=-t_top
    if t_left[1]<0: t_left=-t_left
    p0=P; p1=P+t_left*trim_y_px; p2=p1+t_top*trim_x_px; p3=P+t_top*trim_x_px
    quad=np.array([p0,p1,p2,p3],np.float32)
    h,w=img_shape[:2]
    return _clip_polygon_to_image(quad, w, h)

def _make_corner_ld(left_abc, bottom_abc, trim_x_px, trim_y_px, img_shape):
    aL,bL,cL=left_abc; aB,bB,cB=bottom_abc
    P=_line_intersection(aL,bL,cL, aB,bB,cB)
    if P is None: return np.empty((0,2), np.float32)
    t_bottom=_unit(np.array([-bB,aB],np.float32))
    t_left =_unit(np.array([-bL,aL],np.float32))
    if t_bottom[0]<0: t_bottom=-t_bottom
    if t_left[1]<0:  t_left=-t_left
    p0=P; p1=P+t_left*trim_y_px; p2=p1+t_bottom*trim_x_px; p3=P+t_bottom*trim_x_px
    quad=np.array([p0,p1,p2,p3],np.float32)
    h,w=img_shape[:2]
    return _clip_polygon_to_image(quad, w, h)

def analyze_image(
    filepath,
    trim_ratio_x=0.25, trim_ratio_y=0.12, diff_thresh=15000,
    notch_side="right",
    band_top=10, band_right=10, band_bottom=10,
    corner_exclude_x_px=200, corner_exclude_y_px=25
):
    img = imread_unicode(filepath)
    if img is None: raise RuntimeError(f"画像の読み込みに失敗: {filepath}")
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
    if notch_side == "left":
        pts_side = _extract_edge_points(mask_real, band_right, 'left', corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
    else:
        pts_side = _extract_edge_points(mask_real, band_right, 'right',  corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
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
    if notch_side == "left":
        quad_up=_make_corner_lu((a_top,b_top,c_top),(a_side,b_side,c_side), trim_x_px,trim_y_px,img.shape)
        quad_down=_make_corner_ld((a_side,b_side,c_side),(a_bottom,b_bottom,c_bottom), trim_x_px,trim_y_px,img.shape)
    else:
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

    side_label = "Left" if notch_side == "left" else "Right"
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
class BaslerCamera:
    def __init__(self, device_index=0, timeout_ms=3000):
        self.device_index=device_index
        self.timeout_ms=timeout_ms
        self.cam=None; self.converter=None

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
            self.cam.TriggerSelector.SetValue("FrameStart")
            self.cam.TriggerMode.SetValue("On")
            self.cam.TriggerSource.SetValue("Software")
        except Exception:
            pass
        self._start_grabbing_if_needed()

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

    def snap_bgr(self):
        if not self.is_open():
            self.open()
        self._start_grabbing_if_needed()
        try:
            self.cam.TriggerSoftware.Execute()
        except Exception:
            pass
        res=self.cam.RetrieveResult(self.timeout_ms, pylon.TimeoutHandling_Return)
        if res is None or not res.GrabSucceeded():
            if res is not None: res.Release()
            raise RuntimeError("画像取得に失敗")
        try:
            image=self.converter.Convert(res)
            img=image.GetArray()
            return img
        finally:
            res.Release()

    def __del__(self):
        self.close()


class PLCClient:
    def __init__(self):
        self.cli=None

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
        vals=self.cli.batchread_bitunits(headdevice=head, readsize=1)
        v=int(vals[0]) if isinstance(vals,(list,tuple)) else int(vals)
        return bool(v)

    def write_bit(self, head:str, value:bool):
        self.cli.batchwrite_bitunits(headdevice=head, values=[1 if value else 0])

    def pulse_bit(self, head:str, ms:int=50):
        self.write_bit(head, True)
        time.sleep(max(0,ms)/1000.0)
        self.write_bit(head, False)

    def read_word(self, head:str)->int:
        vals=self.cli.batchread_wordunits(headdevice=head, readsize=1)
        v=int(vals[0]) if isinstance(vals,(list,tuple)) else int(vals)
        return v & 0xFFFF

    def write_word(self, head:str, value:int):
        self.cli.batchwrite_wordunits(headdevice=head, values=[int(value)&0xFFFF])


# ================== 設定 永続化 ==================
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".notch_app_config.json")

@dataclass
class AppConfig:
    # 解析パラメータ
    trim_ratio_x: float = 0.25
    trim_ratio_y: float = 0.12
    diff_thresh: int   = 15000
    band_top: int = 10
    band_right: int = 10
    band_bottom:int = 10
    corner_exclude_x_px:int = 200
    corner_exclude_y_px:int = 25
    auto_preview: bool = True
    notch_side: str = "right"  # "right"|"left"

    # 出力
    output_dir: str = ""

    # カメラ設定
    camera_index: int = 0

    # PLC 設定（メニューバーから編集）
    plc_ip: str = "192.168.1.2"
    plc_port: int = 1026
    dev_trig: str = "M100"
    dev_ru:   str = "M101"
    dev_rd:   str = "M102"
    dev_done: str = "M103"
    dev_busy: str = "M104"
    dev_err_to: str = "M105"
    dev_err_an: str = "M106"
    done_ms: int = 50
    use_sw_trig: bool = True
    timeout_ms: int = 3000

    # ハートビート
    dev_alive: str = "D100"
    alive_ms: int = 1000
    alive_step: int = 1
    alive_auto: bool = False

    # 一時ファイル管理
    temp_max_files: int = 50
    temp_prefixes: list[str] = field(default_factory=lambda: ["BaslerShot_", "PLCshot_"])

    # 結果CSV & PLCショット保存先
    csv_max_records: int = 1000
    plc_shot_dir: str = ""  # 空なら tempdir

    # 自動再接続/監視
    auto_reconnect: bool = True
    auto_watch_on_ready: bool = True

    @staticmethod
    def load():
        try:
            with open(CONFIG_PATH,"r",encoding="utf-8") as f:
                data=json.load(f)
            allowed = {item.name for item in fields(AppConfig)}
            cleaned = {k: v for k, v in data.items() if k in allowed}
            return AppConfig(**cleaned)
        except Exception:
            return AppConfig()

    def save(self):
        try:
            with open(CONFIG_PATH,"w",encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ================== UI: ズーム・パンキャンバス ==================
class ZoomPanCanvas(tk.Canvas):
    def __init__(self, master, bg="#222", **kw):
        super().__init__(master, bg=bg, highlightthickness=0, **kw)
        self._img_pil=None; self._img_tk=None; self._img_id=None
        self.zoom=1.0; self.min_zoom=0.05; self.max_zoom=10.0
        self.offset=np.array([0.0,0.0]); self._drag_start=None
        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._zoom_at(1.1, e.x, e.y))
        self.bind("<Button-5>", lambda e: self._zoom_at(1/1.1, e.x, e.y))

    def set_image(self, pil_image):
        self._img_pil=pil_image
        if self._img_id is None: self.fit_to_window()
        else: self._render()

    def clear(self):
        if self._img_id is not None: self.delete(self._img_id); self._img_id=None
        self._img_pil=None; self._img_tk=None; self.zoom=1.0; self.offset=np.array([0.0,0.0])

    def fit_to_window(self):
        if self._img_pil is None: return
        cw=max(self.winfo_width(),1); ch=max(self.winfo_height(),1)
        iw,ih=self._img_pil.size
        scale=min(cw/iw, ch/ih) if iw and ih else 1.0
        scale=max(self.min_zoom, min(self.max_zoom, scale))
        self.zoom=scale
        self.offset=np.array([(cw - iw*self.zoom)/2.0, (ch - ih*self.zoom)/2.0])
        self._render()

    def set_zoom_100(self):
        if self._img_pil is None: return
        cw=max(self.winfo_width(),1); ch=max(self.winfo_height(),1)
        iw,ih=self._img_pil.size
        self.zoom=1.0
        self.offset=np.array([(cw-iw)/2.0, (ch-ih)/2.0]); self._render()

    def zoom_in(self):  self._zoom_at(1.2, self.winfo_width()/2.0, self.winfo_height()/2.0)
    def zoom_out(self): self._zoom_at(1/1.2, self.winfo_width()/2.0, self.winfo_height()/2.0)

    def _on_configure(self,_): self._render()
    def _on_press(self,e): self._drag_start=np.array([e.x,e.y])
    def _on_drag(self,e):
        if self._drag_start is None: return
        cur=np.array([e.x,e.y]); delta=cur-self._drag_start
        self._drag_start=cur; self.offset+=delta; self._render()
    def _on_release(self,_): self._drag_start=None
    def _on_wheel(self,e):
        if e.delta>0: self._zoom_at(1.1, e.x, e.y)
        elif e.delta<0: self._zoom_at(1/1.1, e.x, e.y)
    def _zoom_at(self, factor, cx, cy):
        if self._img_pil is None: return
        old=self.zoom; new=max(self.min_zoom, min(self.max_zoom, self.zoom*factor))
        if abs(new-old)<1e-6: return
        img_pt=(np.array([cx,cy]) - self.offset)/old
        self.zoom=new; self.offset=np.array([cx,cy]) - img_pt*self.zoom
        self._render()
    def _render(self):
        self.delete("all")
        if self._img_pil is None: return
        iw,ih=self._img_pil.size
        disp=self._img_pil.resize((max(1,int(iw*self.zoom)), max(1,int(ih*self.zoom))), Image.LANCZOS)
        self._img_tk=ImageTk.PhotoImage(disp)
        self._img_id=self.create_image(self.offset[0], self.offset[1], image=self._img_tk, anchor="nw")


# ================== スクロール可能フレーム（左ペイン） ==================
class ScrollFrame(ttk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        canvas = tk.Canvas(self, highlightthickness=0)
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.grid(row=0,column=0,sticky="nsew")
        vbar.grid(row=0,column=1,sticky="ns")
        self.columnconfigure(0,weight=1); self.rowconfigure(0,weight=1)

        self.inner = ttk.Frame(canvas)
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._win = canvas.create_window((0,0), window=self.inner, anchor="nw")
        def _resize(_):
            canvas.itemconfigure(self._win, width=canvas.winfo_width())
        canvas.bind("<Configure>", _resize)


# ================== メインアプリ ==================
class NotchApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("ガラス基板ノッチ判定ツール")
        self.geometry("1500x1000")
        self.minsize(1100, 760)

        # 状態
        self.cfg = AppConfig.load()
        self._trace_lock=False
        self.file_paths=[]
        self.output_dir=self.cfg.output_dir
        self.last_sel_index=None
        self.basler=None
        self.last_result=None; self.last_result_path=None

        # カメラ排他ロック
        self._cam_lock = threading.RLock()

        # 自動プレビュー用 after ジョブID
        self._preview_job = None

        # 解析パラメータ（Tk変数）
        self.trim_ratio_x=tk.DoubleVar(value=self.cfg.trim_ratio_x)
        self.trim_ratio_y=tk.DoubleVar(value=self.cfg.trim_ratio_y)
        self.diff_thresh = tk.IntVar(value=self.cfg.diff_thresh)
        self.band_top=tk.IntVar(value=self.cfg.band_top)
        self.band_right=tk.IntVar(value=self.cfg.band_right)
        self.band_bottom=tk.IntVar(value=self.cfg.band_bottom)
        self.corner_exclude_x_px=tk.IntVar(value=self.cfg.corner_exclude_x_px)
        self.corner_exclude_y_px=tk.IntVar(value=self.cfg.corner_exclude_y_px)
        self.auto_preview=tk.BooleanVar(value=self.cfg.auto_preview)
        self.notch_side=tk.StringVar(value=self.cfg.notch_side)
        self.var_camera_index=tk.IntVar(value=self.cfg.camera_index)

        # PLC/カメラ/ハートビート用
        self.plc=PLCClient()
        self.plc_connected=False
        self.plc_thread=None; self.plc_stop=False; self.prev_trig=False
        self.var_use_sw_trig=tk.BooleanVar(value=self.cfg.use_sw_trig)
        self.var_timeout_ms=tk.IntVar(value=self.cfg.timeout_ms)
        self.var_done_ms=tk.IntVar(value=self.cfg.done_ms)

        # アドレスやIP（メニュー側で編集）
        self.var_plc_ip=tk.StringVar(value=self.cfg.plc_ip)
        self.var_plc_port=tk.IntVar(value=self.cfg.plc_port)
        self.var_dev_trig=tk.StringVar(value=self.cfg.dev_trig)
        self.var_dev_ru=tk.StringVar(value=self.cfg.dev_ru)
        self.var_dev_rd=tk.StringVar(value=self.cfg.dev_rd)
        self.var_dev_done=tk.StringVar(value=self.cfg.dev_done)
        self.var_dev_busy=tk.StringVar(value=self.cfg.dev_busy)
        self.var_dev_err_to=tk.StringVar(value=self.cfg.dev_err_to)
        self.var_dev_err_an=tk.StringVar(value=self.cfg.dev_err_an)

        # 生存カウンタ
        self.hb_thread=None; self.hb_stop=False; self.hb_value=0
        self.var_dev_alive=tk.StringVar(value=self.cfg.dev_alive)
        self.var_alive_ms=tk.IntVar(value=self.cfg.alive_ms)
        self.var_alive_step=tk.IntVar(value=self.cfg.alive_step)
        self.var_alive_auto=tk.BooleanVar(value=self.cfg.alive_auto)

        # 一時ファイル管理
        self.temp_max_files=tk.IntVar(value=self.cfg.temp_max_files)

        # CSV関連
        self.csv_max_records=tk.IntVar(value=self.cfg.csv_max_records)
        self.var_plc_shot_dir=tk.StringVar(value=self.cfg.plc_shot_dir)

        # 連続Grab状態
        self.video_running=False
        self.video_thread=None
        self.video_stop=False

        # 手動操作ガード
        self.manual_stopped=False
        self.manual_disconnected=False

        # ログ（最新5行）
        self._log_lines=deque(maxlen=5)

        # UI
        self._build_menu()
        self._build_ui()
        self._bind_traces()
        self._auto_cleanup_temp_files()
        self._post_status("起動完了。自動接続を試行します。")

        # 起動時の自動接続＆監視
        self.after(300, self._auto_manager_start)

    # ---------- メニュー ----------
    def _build_menu(self):
        menubar=tk.Menu(self)
        self.config(menu=menubar)

        m_settings=tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="設定", menu=m_settings)
        m_settings.add_command(label="PLC連携…", command=self._open_plc_settings)
        m_settings.add_command(label="カメラ設定…", command=self._open_camera_settings)
        m_settings.add_command(label="生存カウンタ…", command=self._open_hb_settings)
        m_settings.add_command(label="一時ファイル管理…", command=self._open_temp_settings)
        m_settings.add_command(label="結果CSV/保存先…", command=self._open_result_settings)
        m_settings.add_separator()
        m_settings.add_command(label="出力フォルダを選択…", command=self.on_pick_outdir)
        m_settings.add_command(label="設定ファイルを開く", command=lambda: os.path.exists(CONFIG_PATH) and os.startfile(CONFIG_PATH))
        m_settings.add_separator()
        m_settings.add_command(label="終了", command=self.destroy)

        # 操作（完了テスト、RU/RDテストはここへ移動）
        m_ops=tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="操作", menu=m_ops)
        m_ops.add_command(label="完了テスト（DONEパルス）", command=self.on_test_done)
        m_ops.add_separator()
        m_ops.add_command(label="RU=1 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_ru.get().strip(), True)))
        m_ops.add_command(label="RU=0 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_ru.get().strip(), False)))
        m_ops.add_command(label="RD=1 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_rd.get().strip(), True)))
        m_ops.add_command(label="RD=0 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_rd.get().strip(), False)))
        m_ops.add_separator()
        m_ops.add_command(label="PLCエラークリア", command=self.on_clear_errors)

    # ---------- メインUI ----------
    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # 左ペイン（スクロール可能） ※左にマージン
        left_wrap=ScrollFrame(self)
        left_wrap.grid(row=0, column=0, sticky="nsw", padx=(12,0))
        left=left_wrap.inner
        left.grid_columnconfigure(0, weight=1, minsize=380)  # 幅不足対策：最低幅

        # 1) 画像入力
        ttk.Label(left, text="1) 画像ファイル / 撮像").grid(row=0, column=0, sticky="w", pady=(4,2))
        # --- 「画像を選ぶ」を単独行に分離 ---
        row_pick=ttk.Frame(left); row_pick.grid(row=1, column=0, sticky="we")
        ttk.Button(row_pick, text="画像を選ぶ（複数可）", command=self.on_pick_files, bootstyle=PRIMARY).pack(side="left")

        # その下の行に 撮像 / 連続Grab開始 / 連続Grab停止
        row_cam=ttk.Frame(left); row_cam.grid(row=2, column=0, sticky="we", pady=(4,0))
        ttk.Button(row_cam, text="撮像（Basler）", command=self.on_capture_basler, bootstyle=SUCCESS).pack(side="left")
        ttk.Button(row_cam, text="連続Grab開始", command=self.on_video_start).pack(side="left", padx=6)
        ttk.Button(row_cam, text="連続Grab停止", command=self.on_video_stop).pack(side="left")

        self.lb_files = tk.Listbox(left, height=10, selectmode=tk.EXTENDED)
        self.lb_files.grid(row=3, column=0, sticky="we")
        self.lb_files.bind("<<ListboxSelect>>", self._on_listbox_select)
        sb=ttk.Scrollbar(left, orient="vertical", command=self.lb_files.yview)
        self.lb_files.configure(yscrollcommand=sb.set); sb.grid(row=3, column=1, sticky="ns")

        # 2) 出力先
        ttk.Label(left, text="2) 出力フォルダ（CSV & 画像）").grid(row=4, column=0, sticky="w", pady=(8,2))
        ttk.Label(left, text=(self.output_dir if self.output_dir else "未指定（元画像と同じ場所）"), bootstyle=INFO).grid(row=5, column=0, sticky="w")

        # 3) 基本パラメータ
        ttk.Label(left, text="3) 基本パラメータ").grid(row=6, column=0, sticky="w", pady=(12,2))
        frm_params=ttk.Frame(left); frm_params.grid(row=7, column=0, sticky="we")
        ttk.Label(frm_params, text="trim_ratio_x:").grid(row=0, column=0, sticky="e")
        ttk.Spinbox(frm_params, from_=0.0, to=0.95, increment=0.01, textvariable=self.trim_ratio_x, width=6).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(frm_params, text="trim_ratio_y:").grid(row=1, column=0, sticky="e")
        ttk.Spinbox(frm_params, from_=0.0, to=0.95, increment=0.01, textvariable=self.trim_ratio_y, width=6).grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(frm_params, text="diff_thresh:").grid(row=2, column=0, sticky="e")
        ttk.Spinbox(frm_params, from_=1, to=1000000, increment=50, textvariable=self.diff_thresh, width=10).grid(row=2, column=1, padx=4, pady=2)

        ttk.Label(frm_params, text="ノッチ位置:").grid(row=3, column=0, sticky="e")
        cmb=ttk.Combobox(
            frm_params,
            state="readonly",
            values=["右上/右下","左上/左下"]
        )
        cmb.grid(row=3, column=1, padx=4, pady=2, sticky="w")
        mode=self.cfg.notch_side
        cmb.set("右上/右下" if mode=="right" else "左上/左下")
        cmb.bind("<<ComboboxSelected>>", self.on_notch_side_change)

        # 4) 直線近似パラメータ
        ttk.Label(left, text="4) 直線近似パラメータ").grid(row=8, column=0, sticky="w", pady=(12,2))
        frm_line=ttk.Frame(left); frm_line.grid(row=9, column=0, sticky="we")
        ttk.Label(frm_line, text="band_top:").grid(row=0, column=0, sticky="e")
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_top, width=6).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(frm_line, text="band_right:").grid(row=1, column=0, sticky="e")
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_right, width=6).grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(frm_line, text="band_bottom:").grid(row=2, column=0, sticky="e")
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_bottom, width=6).grid(row=2, column=1, padx=4, pady=2)
        ttk.Label(frm_line, text="corner_exclude_x_px:").grid(row=3, column=0, sticky="e")
        ttk.Spinbox(frm_line, from_=0, to=500, increment=5, textvariable=self.corner_exclude_x_px, width=6).grid(row=3, column=1, padx=4, pady=2)
        ttk.Label(frm_line, text="corner_exclude_y_px:").grid(row=4, column=0, sticky="e")
        ttk.Spinbox(frm_line, from_=0, to=200, increment=5, textvariable=self.corner_exclude_y_px, width=6).grid(row=4, column=1, padx=4, pady=2)

        ttk.Checkbutton(left, text="パラメータ変更で自動プレビュー", variable=self.auto_preview).grid(row=10, column=0, sticky="w", pady=(8,0))

        # 5) 画像処理 実行
        ttk.Label(left, text="5) 画像処理 実行").grid(row=11, column=0, sticky="w", pady=(8,2))
        frm_btns=ttk.Frame(left); frm_btns.grid(row=12, column=0, sticky="we")
        ttk.Button(frm_btns, text="選択中をプレビュー", command=self.on_preview, bootstyle=PRIMARY).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(frm_btns, text="すべて処理＆保存", command=self.on_batch_process, bootstyle=SUCCESS).grid(row=0, column=1, padx=2, pady=2)

        # 6) PLC 操作（※パラメータ入力は撤去、ボタンのみ残す）
        ttk.Label(left, text="6) PLC 監視・操作").grid(row=13, column=0, sticky="w", pady=(14,4))
        plc=ttk.Labelframe(left, text="PLC Trigger / I/O", padding=8)
        plc.grid(row=14, column=0, sticky="we")

        r_conn=ttk.Frame(plc); r_conn.pack(fill="x", pady=2)
        ttk.Button(r_conn, text="接続", command=self.on_plc_connect, bootstyle=SUCCESS).pack(side="left")
        ttk.Button(r_conn, text="切断", command=self.on_plc_disconnect).pack(side="left", padx=6)
        self.lbl_plc_target=ttk.Label(r_conn, text=f"ターゲット: {self.var_plc_ip.get()}:{self.var_plc_port.get()}", bootstyle=INFO)
        self.lbl_plc_target.pack(side="left", padx=8)

        r_ctrl=ttk.Frame(plc); r_ctrl.pack(fill="x", pady=6)
        ttk.Button(r_ctrl, text="監視開始", command=self.on_plc_watch_start, bootstyle=PRIMARY).pack(side="left")
        ttk.Button(r_ctrl, text="停止", command=lambda: self.on_plc_watch_stop(manual=True)).pack(side="left", padx=6)

        # 右側（プレビュー）
        right=ttk.Frame(self, padding=8); right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1); right.columnconfigure(0, weight=1)
        topbar=ttk.Frame(right); topbar.grid(row=0, column=0, sticky="we")
        ttk.Label(topbar, text="結果プレビュー").pack(side="left")
        self.zoom_label=ttk.Label(topbar, text="100%"); self.zoom_label.pack(side="right", padx=4)
        ttk.Button(topbar, text="100%", command=self.on_zoom_100).pack(side="right")
        ttk.Button(topbar, text="フィット", command=self.on_fit).pack(side="right", padx=(0,6))
        ttk.Button(topbar, text="－", width=3, command=self.on_zoom_out).pack(side="right")
        ttk.Button(topbar, text="＋", width=3, command=self.on_zoom_in).pack(side="right")

        self.preview_area=ttk.Frame(right, relief="groove")
        self.preview_area.grid(row=2, column=0, sticky="nsew", pady=(6,0))
        self.preview_area.rowconfigure(0, weight=1); self.preview_area.columnconfigure(0, weight=1)
        self.canvas=ZoomPanCanvas(self.preview_area, bg="#222"); self.canvas.grid(row=0, column=0, sticky="nsew")

        # ステータス（最新5行固定）
        logframe=ttk.Frame(right); logframe.grid(row=3, column=0, sticky="we", pady=(6,0))
        ttk.Label(logframe, text="ステータス（最新5件）", bootstyle=INFO).pack(anchor="w")
        self.txt_log=tk.Text(logframe, height=5, state="disabled", wrap="none")
        self.txt_log.pack(fill="x")

        self.canvas.bind("<Configure>", lambda _e: self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%"))

    # ---------- 設定ダイアログ ----------
    def _open_plc_settings(self):
        win=tk.Toplevel(self); win.title("PLC連携 設定"); win.transient(self); win.grab_set()
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        # IP/Port
        sec1=ttk.Labelframe(frm, text="接続先", padding=8); sec1.pack(fill="x", pady=6)
        r=ttk.Frame(sec1); r.pack(fill="x")
        ttk.Label(r, text="PLC IP").pack(side="left"); ttk.Entry(r, textvariable=self.var_plc_ip, width=16).pack(side="left", padx=6)
        ttk.Label(r, text="Port").pack(side="left"); ttk.Entry(r, textvariable=self.var_plc_port, width=8).pack(side="left", padx=6)

        # デバイス
        sec2=ttk.Labelframe(frm, text="デバイス割当", padding=8); sec2.pack(fill="x", pady=6)
        grid=ttk.Frame(sec2); grid.pack(fill="x")
        def row(label, var):
            rr=ttk.Frame(grid); rr.pack(fill="x", pady=2)
            ttk.Label(rr, text=label, width=16).pack(side="left")
            ttk.Entry(rr, textvariable=var, width=12).pack(side="left")
        row("トリガ(読)", self.var_dev_trig)
        row("結果RU(書)", self.var_dev_ru)
        row("結果RD(書)", self.var_dev_rd)
        row("完了(パルス)", self.var_dev_done)
        row("ビジー(書)", self.var_dev_busy)
        row("Err Timeout", self.var_dev_err_to)
        row("Err 解析失敗", self.var_dev_err_an)

        # 撮像条件
        sec3=ttk.Labelframe(frm, text="撮像条件", padding=8); sec3.pack(fill="x", pady=6)
        r3=ttk.Frame(sec3); r3.pack(fill="x")
        ttk.Checkbutton(r3, text="ソフトウェアトリガで撮像", variable=self.var_use_sw_trig).pack(side="left")
        ttk.Label(r3, text="撮像Timeout[ms]").pack(side="left", padx=(12,2))
        ttk.Entry(r3, textvariable=self.var_timeout_ms, width=8).pack(side="left", padx=(0,8))
        ttk.Label(r3, text="完了パルス幅[ms]").pack(side="left", padx=(12,2))
        ttk.Entry(r3, textvariable=self.var_done_ms, width=8).pack(side="left")

        ttk.Label(frm, text="変更は即保存されます。閉じるときは右上×で閉じてください。", bootstyle=INFO).pack(anchor="w", pady=(8,0))

        # IP/Port 表示の同期
        def sync_target(*_):
            self.lbl_plc_target.configure(text=f"ターゲット: {self.var_plc_ip.get()}:{self.var_plc_port.get()}")
        self.var_plc_ip.trace_add("write", sync_target)
        self.var_plc_port.trace_add("write", sync_target)

    def _open_camera_settings(self):
        win=tk.Toplevel(self); win.title("カメラ設定"); win.transient(self); win.grab_set()
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="接続するGigEカメラを選択してください。", bootstyle=INFO).pack(anchor="w")
        devices=list_basler_devices()
        if not devices:
            ttk.Label(frm, text="カメラが検出できません。pypylonの導入や接続を確認してください。", bootstyle=WARNING).pack(anchor="w", pady=(8,0))
            return
        labels=[label for _idx, label in devices]
        idx_map={label: idx for idx, label in devices}
        cmb=ttk.Combobox(frm, state="readonly", values=labels)
        current_label=next((label for idx, label in devices if idx==self.var_camera_index.get()), labels[0])
        cmb.set(current_label)
        cmb.pack(anchor="w", pady=(8,0))
        def on_select(_event=None):
            label=cmb.get()
            self.var_camera_index.set(idx_map.get(label, 0))
        cmb.bind("<<ComboboxSelected>>", on_select)
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w", pady=(8,0))

    def _open_hb_settings(self):
        win=tk.Toplevel(self); win.title("生存カウンタ 設定"); win.transient(self); win.grab_set()
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        r=ttk.Frame(frm); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Dデバイス").pack(side="left"); ttk.Entry(r, textvariable=self.var_dev_alive, width=10).pack(side="left", padx=6)
        ttk.Label(r, text="周期[ms]").pack(side="left", padx=(12,2)); ttk.Entry(r, textvariable=self.var_alive_ms, width=8).pack(side="left")
        ttk.Label(r, text="増分").pack(side="left", padx=(12,2)); ttk.Entry(r, textvariable=self.var_alive_step, width=6).pack(side="left")
        ttk.Checkbutton(frm, text="PLC接続時に自動開始", variable=self.var_alive_auto).pack(anchor="w", pady=(8,2))
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w")

    def _open_temp_settings(self):
        win=tk.Toplevel(self); win.title("一時ファイル管理"); win.transient(self); win.grab_set()
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        r=ttk.Frame(frm); r.pack(fill="x", pady=2)
        ttk.Label(r, text="保持上限(枚)").pack(side="left"); ttk.Entry(r, textvariable=self.temp_max_files, width=8).pack(side="left", padx=6)
        ttk.Button(frm, text="今すぐ清掃", command=self._auto_cleanup_temp_files).pack(anchor="w", pady=(8,2))
        ttk.Label(frm, text="BaslerShot_*/PLCshot_* を古い順に削除します。", bootstyle=INFO).pack(anchor="w")

    def _open_result_settings(self):
        win=tk.Toplevel(self); win.title("結果CSV/保存先 設定"); win.transient(self); win.grab_set()
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        r1=ttk.Frame(frm); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="結果CSV 最大レコード数").pack(side="left")
        ttk.Entry(r1, textvariable=self.csv_max_records, width=8).pack(side="left", padx=6)
        r2=ttk.Frame(frm); r2.pack(fill="x", pady=8)
        ttk.Label(r2, text="PLC撮像 画像保存先（空=Temp）").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_plc_shot_dir, width=40).pack(side="left", padx=6)
        ttk.Button(r2, text="参照…", command=self._pick_plcshot_dir).pack(side="left")
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w", pady=(8,0))

    def _pick_plcshot_dir(self):
        d=filedialog.askdirectory(title="PLCトリガで保存する画像の保存先フォルダを選択")
        if d:
            self.var_plc_shot_dir.set(d)

    # ---------- 設定トレース（即保存 + 自動プレビュー） ----------
    def _bind_traces(self):
        """Tk変数の変更を捕捉して保存。解析パラメータは自動プレビューもスケジュール"""
        def save_cfg(*_):
            if self._trace_lock:
                return
            self._sync_cfg_from_vars()
            self.cfg.save()

        # 自動プレビュー対象（解析に影響）
        preview_vars = (
            self.trim_ratio_x, self.trim_ratio_y, self.diff_thresh,
            self.band_top, self.band_right, self.band_bottom,
            self.corner_exclude_x_px, self.corner_exclude_y_px,
            self.notch_side,
            self.auto_preview,  # ONにした瞬間にもプレビューしたい
        )
        # 保存のみ対象（PLC/HB/保存先 他）
        non_preview_vars = (
            self.var_plc_ip, self.var_plc_port, self.var_dev_trig, self.var_dev_ru, self.var_dev_rd,
            self.var_dev_done, self.var_dev_busy, self.var_dev_err_to, self.var_dev_err_an,
            self.var_use_sw_trig, self.var_timeout_ms, self.var_done_ms,
            self.var_dev_alive, self.var_alive_ms, self.var_alive_step, self.var_alive_auto,
            self.temp_max_files, self.csv_max_records, self.var_plc_shot_dir,
            self.var_camera_index
        )

        def bind_with_preview(v):
            v.trace_add("write", lambda *args: (save_cfg(), self._schedule_auto_preview()))
        def bind_save_only(v):
            v.trace_add("write", lambda *args: save_cfg())

        for v in preview_vars: bind_with_preview(v)
        for v in non_preview_vars: bind_save_only(v)

    def _schedule_auto_preview(self):
        """パラメータ変更時の自動プレビュー（200msデバウンス）"""
        try:
            if not bool(self.auto_preview.get()):
                return
        except Exception:
            return
        if not self.file_paths:
            return
        if self.last_sel_index is None and not self.lb_files.curselection():
            return
        if getattr(self, "video_running", False):
            return
        if self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(200, self.on_preview)

    def _sync_cfg_from_vars(self):
        self.cfg.trim_ratio_x=self.trim_ratio_x.get()
        self.cfg.trim_ratio_y=self.trim_ratio_y.get()
        self.cfg.diff_thresh=self.diff_thresh.get()
        self.cfg.band_top=self.band_top.get()
        self.cfg.band_right=self.band_right.get()
        self.cfg.band_bottom=self.band_bottom.get()
        self.cfg.corner_exclude_x_px=self.corner_exclude_x_px.get()
        self.cfg.corner_exclude_y_px=self.corner_exclude_y_px.get()
        self.cfg.auto_preview=bool(self.auto_preview.get())
        self.cfg.notch_side=self.notch_side.get().strip() or "right"
        self.cfg.camera_index=int(self.var_camera_index.get())
        self.cfg.output_dir=self.output_dir or ""
        self.cfg.plc_ip=self.var_plc_ip.get().strip()
        self.cfg.plc_port=int(self.var_plc_port.get())
        self.cfg.dev_trig=self.var_dev_trig.get().strip()
        self.cfg.dev_ru=self.var_dev_ru.get().strip()
        self.cfg.dev_rd=self.var_dev_rd.get().strip()
        self.cfg.dev_done=self.var_dev_done.get().strip()
        self.cfg.dev_busy=self.var_dev_busy.get().strip()
        self.cfg.dev_err_to=self.var_dev_err_to.get().strip()
        self.cfg.dev_err_an=self.var_dev_err_an.get().strip()
        self.cfg.use_sw_trig=bool(self.var_use_sw_trig.get())
        self.cfg.timeout_ms=int(self.var_timeout_ms.get())
        self.cfg.done_ms=int(self.var_done_ms.get())
        self.cfg.dev_alive=self.var_dev_alive.get().strip()
        self.cfg.alive_ms=int(self.var_alive_ms.get())
        self.cfg.alive_step=int(self.var_alive_step.get())
        self.cfg.alive_auto=bool(self.var_alive_auto.get())
        self.cfg.temp_max_files=int(self.temp_max_files.get())
        self.cfg.csv_max_records=int(self.csv_max_records.get())
        self.cfg.plc_shot_dir=self.var_plc_shot_dir.get().strip()

    # ---------- 左ペイン操作 ----------
    def _on_listbox_select(self,_evt=None):
        sel=self.lb_files.curselection()
        if sel:
            self.last_sel_index=sel[0]
            if self.auto_preview.get(): self.on_preview()

    def on_pick_files(self):
        paths=filedialog.askopenfilenames(
            title="画像を選択してください（複数選択可）",
            filetypes=[("画像ファイル","*.bmp;*.jpg;*.jpeg;*.png"),("すべてのファイル","*.*")]
        )
        if not paths: return
        self.file_paths=list(paths)
        self.lb_files.delete(0, tk.END)
        for p in self.file_paths: self.lb_files.insert(tk.END, p)
        self.lb_files.selection_set(0); self.lb_files.activate(0)
        self.last_sel_index=0
        if self.auto_preview.get(): self.on_preview()
        self._post_status(f"{len(self.file_paths)} 件のファイルを読み込み")

    def on_pick_outdir(self):
        d=filedialog.askdirectory(title="CSVと結果画像の出力先フォルダを選択してください")
        if d:
            self.output_dir=d
            self._sync_cfg_from_vars(); self.cfg.save()
            self._post_status(f"出力先を設定: {self.output_dir}")

    def on_notch_side_change(self, event=None):
        val=event.widget.get()
        self.cfg.notch_side="left" if val=="左上/左下" else "right"
        self.cfg.save()
        if self.auto_preview.get(): self.on_preview()

    def on_zoom_in(self):
        self.canvas.zoom_in(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
    def on_zoom_out(self):
        self.canvas.zoom_out(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
    def on_fit(self):
        self.canvas.fit_to_window(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
    def on_zoom_100(self):
        self.canvas.set_zoom_100(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")

    def on_preview(self):
        try:
            idx=self.last_sel_index
            if idx is None:
                sel=self.lb_files.curselection()
                if not sel: self._post_status("プレビュー対象が選択されていません"); return
                idx=sel[0]; self.last_sel_index=idx
            if not (0<=idx<len(self.file_paths)): self._post_status("有効な画像が選択されていません"); return
            path=self.file_paths[idx]
            res=analyze_image(
                path,
                trim_ratio_x=self.trim_ratio_x.get(),
                trim_ratio_y=self.trim_ratio_y.get(),
                diff_thresh=self.diff_thresh.get(),
                notch_side=self.notch_side.get(),
                band_top=self.band_top.get(),
                band_right=self.band_right.get(),
                band_bottom=self.band_bottom.get(),
                corner_exclude_x_px=self.corner_exclude_x_px.get(),
                corner_exclude_y_px=self.corner_exclude_y_px.get()
            )
            self._show_preview(path, res)
        except Exception as e:
            traceback.print_exc(); self._post_status(f"[エラー:プレビュー] {e}")

    def on_batch_process(self):
        try:
            if not self.file_paths:
                self._post_status("処理する画像が選択されていません"); return
            csv_path=self._get_result_csv_path()
            header=["filename","folderpath","trim_ratio_x","trim_ratio_y","diff_thresh","notch_side",
                    "band_top","band_right","band_bottom","corner_exclude_x_px","corner_exclude_y_px",
                    "top_angle_deg","side_angle_deg","bottom_angle_deg",
                    "top_slope","side_slope","bottom_slope",
                    "ru_area","ru_result","rd_area","rd_result","result_img"]
            count_ok=0
            for path in self.file_paths:
                try:
                    res=analyze_image(
                        path,
                        trim_ratio_x=self.trim_ratio_x.get(),
                        trim_ratio_y=self.trim_ratio_y.get(),
                        diff_thresh=self.diff_thresh.get(),
                        notch_side=self.notch_side.get(),
                        band_top=self.band_top.get(),
                        band_right=self.band_right.get(),
                        band_bottom=self.band_bottom.get(),
                        corner_exclude_x_px=self.corner_exclude_x_px.get(),
                        corner_exclude_y_px=self.corner_exclude_y_px.get()
                    )
                    out_path=save_result_image(res["img_bgr"], path, self.output_dir)
                    row=[os.path.basename(path), os.path.dirname(path),
                         self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
                         self.notch_side.get(),
                         self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
                         self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
                         res["top_angle_deg"], res["side_angle_deg"], res["bottom_angle_deg"],
                         res["top_slope"], res["side_slope"], res["bottom_slope"],
                         res["ru_area"], res["ru_result"], res["rd_area"], res["rd_result"],
                         out_path or ""]
                    self._append_result_csv(csv_path, header, row)
                    count_ok+=1
                except Exception as ie:
                    traceback.print_exc(); self._post_status(f"[警告] 失敗: {path} : {ie}")
            self._post_status(f"バッチ完了: {count_ok}件 / CSV: {csv_path}")
        except Exception as e:
            traceback.print_exc(); self._post_status(f"[エラー:バッチ処理] {e}")

    def _show_preview(self, path, result_dict):
        bgr=result_dict["img_bgr"]; rgb=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self.canvas.set_image(Image.fromarray(rgb))
        self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
        top_p1, top_p2 = result_dict["top_line"]
        side_p1, side_p2 = result_dict["side_line"]
        bottom_p1, bottom_p2 = result_dict["bottom_line"]
        info=(f"ファイル: {os.path.basename(path)} | "
              f"RU: {result_dict['ru_result']} ({result_dict['ru_area']}) | "
              f"RD: {result_dict['rd_result']} ({result_dict['rd_area']}) | "
              f"Top傾き: {result_dict['top_angle_deg']:.3f}° "
              f"{result_dict['side_label']}傾き: {result_dict['side_angle_deg']:.3f}° "
              f"Bottom傾き: {result_dict['bottom_angle_deg']:.3f}° | "
              f"Top線: {top_p1}->{top_p2} "
              f"{result_dict['side_label']}線: {side_p1}->{side_p2} "
              f"Bottom線: {bottom_p1}->{bottom_p2} | "
              f"trim=({self.trim_ratio_x.get():.2f},{self.trim_ratio_y.get():.2f}) "
              f"th={self.diff_thresh.get()} "
              f"[bands=({self.band_top.get()},{self.band_right.get()},{self.band_bottom.get()}), "
              f"exclude=({self.corner_exclude_x_px.get()},{self.corner_exclude_y_px.get()})]")
        self._post_status(info)
        self.last_result=result_dict; self.last_result_path=path

    # ---------- カメラ共通ヘルパ（スレッド安全） ----------
    def _cam_open_if_needed(self):
        with self._cam_lock:
            if self.basler is None:
                self.basler = BaslerCamera(device_index=self.var_camera_index.get(), timeout_ms=self.var_timeout_ms.get())
                self.basler.open()
            else:
                if not self.basler.is_healthy():
                    self.basler.reopen()
            return self.basler

    def _cam_close_and_null(self):
        with self._cam_lock:
            try:
                if self.basler:
                    self.basler.close()
            except Exception:
                pass
            self.basler = None

    def _cam_snap_bgr(self):
        # 1回目
        with self._cam_lock:
            cam = self._cam_open_if_needed()
            try:
                return cam.snap_bgr()
            except Exception:
                try:
                    cam.reopen()
                except Exception:
                    self.basler = None
                    raise
        # 2回目
        with self._cam_lock:
            cam = self._cam_open_if_needed()
            return cam.snap_bgr()

    # ---------- 単発撮像/連続Grab ----------
    def on_capture_basler(self):
        if self.video_running:
            self._post_status("連続Grab停止中のみ単発撮像が可能です。先に［連続Grab停止］してください。")
            return
        try:
            if not HAS_PYLYON:
                self._post_status("pypylon が見つかりません。Basler Pylon と pypylon を導入してください。"); return
            img_bgr=self._cam_snap_bgr()
            ts=time.strftime("%Y%m%d_%H%M%S")
            tmp_path=os.path.join(tempfile.gettempdir(), f"BaslerShot_{ts}.png")
            ok, buf=cv2.imencode(".png", img_bgr)
            if not ok: raise RuntimeError("撮像画像のエンコードに失敗")
            buf.tofile(tmp_path)
            self._auto_cleanup_temp_files()
            self.file_paths.append(tmp_path)
            self.lb_files.insert(tk.END, tmp_path)
            self.last_sel_index=len(self.file_paths)-1
            self.lb_files.selection_clear(0, tk.END); self.lb_files.selection_set(tk.END); self.lb_files.activate(tk.END)
            if self.auto_preview.get(): self.on_preview()
            self._post_status(f"撮像: {tmp_path}")
        except Exception as e:
            traceback.print_exc(); self._post_status(f"[エラー:撮像] {e}")

    def on_video_start(self):
        if self.video_running:
            self._post_status("すでに連続Grab中です")
            return
        if not HAS_PYLYON:
            self._post_status("pypylon が見つかりません。Basler Pylon と pypylon を導入してください。"); return
        self.video_stop=False
        self.video_running=True
        self.video_thread=threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()
        self._post_status("連続Grab開始")

    def on_video_stop(self):
        if not self.video_running:
            self._post_status("連続Grabは動作していません")
            return
        self.video_stop=True
        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join(timeout=1.0)
        self.video_thread=None
        self.video_running=False
        self._post_status("連続Grab停止")

    def _video_loop(self):
        target_fps = 15.0
        period = 1.0 / target_fps
        last_log_err = 0.0
        while not self.video_stop:
            t0 = time.monotonic()
            try:
                img_bgr = self._cam_snap_bgr()
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
                self.after(0, lambda im=pil: self.canvas.set_image(im))
            except Exception as e:
                if time.monotonic() - last_log_err > 1.5:
                    self._post_status(f"連続Grab: 撮像エラー: {e}")
                    last_log_err = time.monotonic()
                time.sleep(0.2)
            dt = time.monotonic() - t0
            if dt < period:
                time.sleep(max(0.0, period - dt))

    # ---------- PLC 接続/監視 ----------
    def on_plc_connect(self):
        try:
            # self.plc が None の場合は再生成してから接続
            if self.plc is None:
                self.plc = PLCClient()
            self.plc.connect(self.var_plc_ip.get().strip(), int(self.var_plc_port.get()))
            self.plc_connected=True
            self.manual_disconnected=False
            self._post_status("PLC接続OK")
            if self.var_alive_auto.get():
                self._hb_start_if_needed()
        except Exception as e:
            self.plc_connected=False
            self._post_status(f"[PLC接続エラー] {e}")

    def on_plc_disconnect(self):
        try:
            self.manual_disconnected=True
            self.on_plc_watch_stop(manual=True)
            self._hb_stop()
            if self.plc:
                self.plc.close()
        finally:
            self.plc_connected=False
            self._post_status("PLC切断しました")

    def on_test_done(self):
        self._safe_plc(lambda: self.plc.pulse_bit(self.var_dev_done.get().strip(), self.var_done_ms.get()))

    def on_clear_errors(self):
        def _clear():
            self.plc.write_bit(self.var_dev_err_to.get().strip(), False)
            self.plc.write_bit(self.var_dev_err_an.get().strip(), False)
        self._safe_plc(_clear, quiet=True)
        self._post_status("PLCエラークリア書込み")

    def on_plc_watch_start(self):
        if not self.plc_connected:
            self._post_status("PLC 未接続です。先に接続してください。"); return
        if not HAS_PYLYON:
            self._post_status("pypylon がありません。"); return
        try:
            self._cam_open_if_needed()
        except Exception as e:
            self._post_status(f"カメラ初期化に失敗: {e}"); return
        if self.plc_thread and self.plc_thread.is_alive():
            self._post_status("既に監視中です"); return
        self.plc_stop=False; self.prev_trig=False
        self.manual_stopped=False
        self.plc_thread=threading.Thread(target=self._plc_loop, daemon=True); self.plc_thread.start()
        self._post_status("トリガ監視開始")

    def on_plc_watch_stop(self, manual:bool=True):
        self.manual_stopped = bool(manual)
        self.plc_stop=True
        if self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.join(timeout=1.0)
        self.plc_thread=None
        self._post_status("トリガ監視停止")

    def _plc_loop(self):
        poll=0.01
        while not self.plc_stop:
            try:
                trig=self.plc.read_bit(self.var_dev_trig.get().strip())
            except Exception as e:
                self._post_status(f"PLC読取エラー: {e}")
                time.sleep(0.2); continue

            if trig and not self.prev_trig:
                self._post_status("トリガ検出: 撮像→解析→返答")
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_busy.get().strip(), True), quiet=True)
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_err_to.get().strip(), False), quiet=True)
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_err_an.get().strip(), False), quiet=True)

                ok_capture=True; img_tmp_path=None
                error_type=None
                try:
                    shot_dir = self.cfg.plc_shot_dir if self.cfg.plc_shot_dir else tempfile.gettempdir()
                    os.makedirs(shot_dir, exist_ok=True)
                    ts=time.strftime("%Y%m%d_%H%M%S")
                    img_tmp_path=os.path.join(shot_dir, f"PLCshot_{ts}.png")

                    img_bgr = self._cam_snap_bgr()

                    ok, buf=cv2.imencode(".png", img_bgr)
                    if ok:
                        buf.tofile(img_tmp_path)
                        self._auto_cleanup_temp_files()
                    else:
                        ok_capture=False
                        error_type="CAPTURE"
                except Exception as e:
                    ok_capture=False
                    msg=str(e).lower()
                    error_type = "TIMEOUT" if ("timeout" in msg or "time out" in msg) else "CAPTURE"
                    self._post_status(f"撮像エラー: {e}")
                    self._cam_close_and_null()

                ru_notch=False; rd_notch=False; to_error=False; an_error=False
                csv_path=self._get_result_csv_path()
                header=["filename","folderpath","trim_ratio_x","trim_ratio_y","diff_thresh","notch_side",
                        "band_top","band_right","band_bottom","corner_exclude_x_px","corner_exclude_y_px",
                        "top_angle_deg","side_angle_deg","bottom_angle_deg",
                        "top_slope","side_slope","bottom_slope",
                        "ru_area","ru_result","rd_area","rd_result","result_img"]

                if ok_capture and img_tmp_path:
                    try:
                        res=analyze_image(
                            img_tmp_path,
                            trim_ratio_x=self.trim_ratio_x.get(),
                            trim_ratio_y=self.trim_ratio_y.get(),
                            diff_thresh=self.diff_thresh.get(),
                            notch_side=self.notch_side.get(),
                            band_top=self.band_top.get(),
                            band_right=self.band_right.get(),
                            band_bottom=self.band_bottom.get(),
                            corner_exclude_x_px=self.corner_exclude_x_px.get(),
                            corner_exclude_y_px=self.corner_exclude_y_px.get()
                        )
                        ru_notch=(res["ru_result"]=="NOTCH"); rd_notch=(res["rd_result"]=="NOTCH")
                        self._post_preview(img_tmp_path, res)
                        self.file_paths.append(img_tmp_path); self._post_list_add(img_tmp_path)

                        result_img_path = save_result_image(res["img_bgr"], img_tmp_path, self.output_dir or os.path.dirname(img_tmp_path))
                        row=[os.path.basename(img_tmp_path), os.path.dirname(img_tmp_path),
                             self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
                             self.notch_side.get(),
                             self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
                             self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
                             res["top_angle_deg"], res["side_angle_deg"], res["bottom_angle_deg"],
                             res["top_slope"], res["side_slope"], res["bottom_slope"],
                             res["ru_area"], res["ru_result"], res["rd_area"], res["rd_result"],
                             result_img_path or ""]
                        self._append_result_csv(csv_path, header, row)
                    except Exception as e:
                        an_error=True
                        self._post_status(f"解析エラー: {e}")
                        row=[os.path.basename(img_tmp_path) if img_tmp_path else "",
                             os.path.dirname(img_tmp_path) if img_tmp_path else "",
                             self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
                             self.notch_side.get(),
                             self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
                             self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
                             "", "", "", "", "", "",
                             -1, "ERROR_ANALYZE", -1, "ERROR_ANALYZE", ""]
                        self._append_result_csv(csv_path, header, row)
                else:
                    to_error=True
                    row=["", self.cfg.plc_shot_dir or tempfile.gettempdir(),
                         self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
                         self.notch_side.get(),
                         self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
                         self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
                         "", "", "", "", "", "",
                         -1, "ERROR_TIMEOUT" if (error_type=="TIMEOUT") else "ERROR_CAPTURE",
                         -1, "ERROR_TIMEOUT" if (error_type=="TIMEOUT") else "ERROR_CAPTURE",
                         ""]
                    self._append_result_csv(csv_path, header, row)

                # PLCへ返答
                try:
                    self.plc.write_bit(self.var_dev_ru.get().strip(), bool(ru_notch))
                    self.plc.write_bit(self.var_dev_rd.get().strip(), bool(rd_notch))
                    if to_error: self.plc.write_bit(self.var_dev_err_to.get().strip(), True)
                    if an_error: self.plc.write_bit(self.var_dev_err_an.get().strip(), True)
                except Exception as e:
                    self._post_status(f"結果/エラー書込エラー: {e}")

                # 完了パルス
                try:
                    self.plc.pulse_bit(self.var_dev_done.get().strip(), self.var_done_ms.get())
                except Exception as e:
                    self._post_status(f"完了パルスエラー: {e}")

                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_busy.get().strip(), False), quiet=True)
                self._post_status(f"返答: RU={int(ru_notch)} RD={int(rd_notch)} TO_ERR={int(to_error)} AN_ERR={int(an_error)}")

            self.prev_trig=trig
            time.sleep(poll)

    # ---------- ハートビート ----------
    def _hb_start_if_needed(self):
        if not self.plc_connected: return
        if not self.var_alive_auto.get(): return
        if self.hb_thread and self.hb_thread.is_alive(): return
        self.hb_stop=False
        try:
            self.hb_value=self.plc.read_word(self.var_dev_alive.get().strip())
        except Exception:
            self.hb_value=0
        self.hb_thread=threading.Thread(target=self._hb_loop, daemon=True); self.hb_thread.start()
        self._post_status("HB自動開始")

    def _hb_stop(self):
        self.hb_stop=True
        if self.hb_thread and self.hb_thread.is_alive():
            self.hb_thread.join(timeout=1.0)
        self.hb_thread=None
        self._post_status("HB停止")

    def _hb_loop(self):
        last_err=0.0
        while not self.hb_stop:
            if not self.plc_connected:
                time.sleep(0.5); continue
            try:
                interval=max(10, int(self.var_alive_ms.get()))
                step=max(1, int(self.var_alive_step.get()))
                self.hb_value=(self.hb_value+step)&0xFFFF
                self.plc.write_word(self.var_dev_alive.get().strip(), self.hb_value)
            except Exception as e:
                now=time.monotonic()
                if now-last_err>1.5:
                    self._post_status(f"HB書込エラー: {e}")
                    last_err=now
            time.sleep(max(10, int(self.var_alive_ms.get()))/1000.0)

    # ---------- 自動再接続マネージャ ----------
    def _auto_manager_start(self):
        threading.Thread(target=self._auto_manager_loop, daemon=True).start()

    def _auto_manager_loop(self):
        plc_backoff=1.0; cam_backoff=1.0
        while True:
            try:
                if self.cfg.auto_reconnect and not self.manual_disconnected:
                    # PLC 自動接続
                    if not self.plc_connected:
                        try:
                            self.on_plc_connect()
                            plc_backoff=1.0
                        except Exception as e:
                            self._post_status(f"自動PLC接続失敗: {e}")
                            plc_backoff=min(plc_backoff*1.5, 10.0)
                            time.sleep(plc_backoff)

                    # カメラ（連続Grab中は触らない）
                    if self.plc_connected:
                        if self.video_running:
                            pass
                        else:
                            need_cam=False
                            if not HAS_PYLYON:
                                self._post_status("pypylon 未導入のためカメラ自動接続不可")
                            else:
                                with self._cam_lock:
                                    if self.basler is None:
                                        need_cam=True
                                    else:
                                        try:
                                            if not self.basler.is_healthy():
                                                need_cam=True
                                        except Exception:
                                            need_cam=True
                                if need_cam:
                                    try:
                                        self._cam_open_if_needed()
                                        cam_backoff=1.0
                                        self._post_status("カメラ接続OK")
                                    except Exception as e:
                                        self._cam_close_and_null()
                                        self._post_status(f"カメラ接続失敗: {e}")
                                        cam_backoff=min(cam_backoff*1.5, 10.0)
                                        time.sleep(cam_backoff)

                    # READY なら監視を自動開始（手動停止していないとき）
                    if self.plc_connected and (self.basler is not None) and self.cfg.auto_watch_on_ready and not self.manual_stopped:
                        if not (self.plc_thread and self.plc_thread.is_alive()):
                            self.on_plc_watch_start()

                # 監視中の断検知（PLC）
                if self.plc_thread and self.plc_thread.is_alive():
                    try:
                        _ = self.plc.read_bit(self.var_dev_trig.get().strip())
                    except Exception as e:
                        self._post_status(f"PLC通信断検知: {e}")
                        self._hb_stop()
                        self.on_plc_watch_stop(manual=False)
                        try:
                            if self.plc: self.plc.close()
                        except: pass
                        self.plc_connected=False
                time.sleep(0.8)
            except Exception as e:
                self._post_status(f"[Auto] 例外: {e}")
                time.sleep(1.0)

    # ---------- ステータス/スレッド安全UI ----------
    def _post_status(self, text):
        stamp=f"{time.strftime('%H:%M:%S')} | {text}"
        self._log_lines.appendleft(stamp)
        def _update():
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            self.txt_log.insert("1.0", "\n".join(list(self._log_lines)))
            self.txt_log.configure(state="disabled")
        try:
            self.after(0, _update)
        except Exception:
            pass

    def _post_preview(self, path, resdict):
        try:
            self.after(0, lambda: self._show_preview(path, resdict))
        except Exception:
            pass

    def _post_list_add(self, path):
        try:
            self.after(0, lambda: (self.lb_files.insert(tk.END, path),
                                   self.lb_files.selection_clear(0, tk.END),
                                   self.lb_files.selection_set(tk.END)))
        except Exception:
            pass

    def _safe_plc(self, func, quiet=False):
        try:
            func()
            if not quiet: self._post_status("PLC OK")
        except Exception as e:
            if not quiet: self._post_status(f"[PLCエラー] {e}")

    # ---------- 結果CSVユーティリティ（最大レコード数ローテーション） ----------
    def _get_result_csv_path(self):
        base = self.output_dir if self.output_dir else (self.cfg.plc_shot_dir or tempfile.gettempdir())
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "result.csv")

    def _append_result_csv(self, csv_path, header, row):
        max_records = max(1, int(self.csv_max_records.get()))
        rows=[]
        if os.path.isfile(csv_path):
            try:
                with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                    r=csv.reader(f)
                    existing=list(r)
                if existing:
                    if existing[0]==header:
                        rows=existing[1:]
                    else:
                        rows=existing
            except Exception:
                rows=[]
        rows.append([*row])
        if len(rows)>max_records:
            rows = rows[-max_records:]
        d=os.path.dirname(csv_path)
        if d: os.makedirs(d, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w=csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    # ---------- 一時ファイル清掃 ----------
    def _auto_cleanup_temp_files(self):
        try:
            max_files=int(self.temp_max_files.get())
            if max_files<=0: return
            patterns=[os.path.join(tempfile.gettempdir(), f"{p}*.png") for p in self.cfg.temp_prefixes]
            files=[]
            for pat in patterns:
                files.extend(glob.glob(pat))
            files=sorted(files, key=lambda p: os.path.getmtime(p))
            if len(files)>max_files:
                remove=files[0:len(files)-max_files]
                for f in remove:
                    try: os.remove(f)
                    except Exception: pass
                self._post_status(f"一時ファイル清掃: {len(remove)} 件削除（上限 {max_files}）")
        except Exception as e:
            self._post_status(f"[Temp清掃エラー] {e}")

    # ---------- 終了 ----------
    def destroy(self):
        try:
            self.on_plc_watch_stop(manual=True)
            self._hb_stop()
            if self.plc_connected and self.plc:
                try: self.plc.close()
                except: pass
            if self.basler is not None:
                try: self.basler.close()
                except: pass
            self._sync_cfg_from_vars(); self.cfg.save()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    app=NotchApp()
    app.mainloop()
