# -*- coding: utf-8 -*-
"""
notch_app.py の全行に対して、日本語の解説コメントを追加した注釈版。
自動生成ファイルです。実行用途ではなく読解用途で使用してください。
"""

# [解説 0001] この行の意図を確認するための注釈行です。
# -*- coding: utf-8 -*-
# [解説 0002] この行の意図を確認するための注釈行です。
"""
# [解説 0003] この行の意図を確認するための注釈行です。
ガラス基板ノッチ判定ツール（Basler撮像 + PLC返答 + 自動再接続 + 一時ファイル上限 + CSVローテーション + 連続Grab）
# [解説 0004] この行の意図を確認するための注釈行です。
- 解析は直線近似のみ（RU/RD）
# [解説 0005] この行の意図を確認するための注釈行です。
- すべての通知はステータス（最新5行固定）に集約（ダイアログ非使用）
# [解説 0006] この行の意図を確認するための注釈行です。
- 設定は自動保存/復元（ユーザホーム: ~/.notch_app_config.json）
# [解説 0007] この行の意図を確認するための注釈行です。
- 左ペインは全体スクロール & 左にマージン & 幅改善
# [解説 0008] この行の意図を確認するための注釈行です。
- 起動時/断時の自動再接続→監視開始（手動停止/切断時は除外）
# [解説 0009] この行の意図を確認するための注釈行です。
- PLC 連携のパラメータ入力 UI はメインから撤去（ボタンは残す）
# [解説 0010] この行の意図を確認するための注釈行です。
- RU/RD/完了テストはメニューバー「操作」に移動（メイン画面から削除）
# [解説 0011] この行の意図を確認するための注釈行です。
- 連続Grab（動画）開始/停止（手動時のみ）を追加
# [解説 0012] この行の意図を確認するための注釈行です。
- PLCトリガ結果も result.csv に追記（エラーはエラーと記録）
# [解説 0013] この行の意図を確認するための注釈行です。
- result.csv は最大レコード数を設定可。超過時は古い行から上書き（ローテーション）
# [解説 0014] この行の意図を確認するための注釈行です。
- PLCトリガで保存する画像の保存先を設定可（空ならTemp）
# [解説 0015] この行の意図を確認するための注釈行です。
- パラメータ変更時は200msデバウンス付きで自動プレビュー更新
# [解説 0016] この行の意図を確認するための注釈行です。
"""
# [解説 0017] この行の意図を確認するための注釈行です。

# [解説 0018] この行の意図を確認するための注釈行です。
import cv2
# [解説 0019] この行の意図を確認するための注釈行です。
import numpy as np
# [解説 0020] この行の意図を確認するための注釈行です。
import tkinter as tk
# [解説 0021] この行の意図を確認するための注釈行です。
from tkinter import filedialog
# [解説 0022] この行の意図を確認するための注釈行です。
import ttkbootstrap as ttk
# [解説 0023] この行の意図を確認するための注釈行です。
from ttkbootstrap.constants import *
# [解説 0024] この行の意図を確認するための注釈行です。
from PIL import Image, ImageTk
# [解説 0025] この行の意図を確認するための注釈行です。
import csv, os, re, traceback, tempfile, time, json, glob, threading
# [解説 0026] この行の意図を確認するための注釈行です。
from dataclasses import dataclass, asdict, field, fields
# [解説 0027] この行の意図を確認するための注釈行です。
from collections import deque
# [解説 0028] この行の意図を確認するための注釈行です。

# [解説 0029] この行の意図を確認するための注釈行です。
# ====== オプション依存（存在チェック） ======
# [解説 0030] この行の意図を確認するための注釈行です。
try:
# [解説 0031] この行の意図を確認するための注釈行です。
    from pypylon import pylon
# [解説 0032] この行の意図を確認するための注釈行です。
    HAS_PYLYON = True
# [解説 0033] この行の意図を確認するための注釈行です。
except Exception:
# [解説 0034] この行の意図を確認するための注釈行です。
    HAS_PYLYON = False
# [解説 0035] この行の意図を確認するための注釈行です。

# [解説 0036] この行の意図を確認するための注釈行です。
try:
# [解説 0037] この行の意図を確認するための注釈行です。
    import pymcprotocol
# [解説 0038] この行の意図を確認するための注釈行です。
    HAS_PYMC = True
# [解説 0039] この行の意図を確認するための注釈行です。
except Exception:
# [解説 0040] この行の意図を確認するための注釈行です。
    HAS_PYMC = False
# [解説 0041] この行の意図を確認するための注釈行です。

# [解説 0042] この行の意図を確認するための注釈行です。

# [解説 0043] この行の意図を確認するための注釈行です。
# ================== 低レベルユーティリティ ==================
# [解説 0044] この行の意図を確認するための注釈行です。
def imread_unicode(filename):
# [解説 0045] この行の意図を確認するための注釈行です。
    data = np.fromfile(filename, dtype=np.uint8)
# [解説 0046] この行の意図を確認するための注釈行です。
    return cv2.imdecode(data, cv2.IMREAD_COLOR)
# [解説 0047] この行の意図を確認するための注釈行です。

# [解説 0048] この行の意図を確認するための注釈行です。
def save_to_csv(csv_path, row, header=None):
# [解説 0049] この行の意図を確認するための注釈行です。
    d = os.path.dirname(csv_path)
# [解説 0050] この行の意図を確認するための注釈行です。
    if d: os.makedirs(d, exist_ok=True)
# [解説 0051] この行の意図を確認するための注釈行です。
    exists = os.path.isfile(csv_path)
# [解説 0052] この行の意図を確認するための注釈行です。
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
# [解説 0053] この行の意図を確認するための注釈行です。
        w = csv.writer(f)
# [解説 0054] この行の意図を確認するための注釈行です。
        if (header is not None) and (not exists):
# [解説 0055] この行の意図を確認するための注釈行です。
            w.writerow(header)
# [解説 0056] この行の意図を確認するための注釈行です。
        w.writerow(row)
# [解説 0057] この行の意図を確認するための注釈行です。

# [解説 0058] この行の意図を確認するための注釈行です。
def safe_filename(name):
# [解説 0059] この行の意図を確認するための注釈行です。
    return re.sub(r'[\\/:*?"<>|]', "_", name)
# [解説 0060] この行の意図を確認するための注釈行です。

# [解説 0061] この行の意図を確認するための注釈行です。
def save_result_image(img_bgr, src_filepath, out_dir):
# [解説 0062] この行の意図を確認するための注釈行です。
    try:
# [解説 0063] この行の意図を確認するための注釈行です。
        filename_only = os.path.basename(src_filepath)
# [解説 0064] この行の意図を確認するための注釈行です。
        stem, _ = os.path.splitext(filename_only)
# [解説 0065] この行の意図を確認するための注釈行です。
        stem = safe_filename(stem)
# [解説 0066] この行の意図を確認するための注釈行です。
        save_dir = out_dir if out_dir else os.path.dirname(src_filepath) or tempfile.gettempdir()
# [解説 0067] この行の意図を確認するための注釈行です。
        os.makedirs(save_dir, exist_ok=True)
# [解説 0068] この行の意図を確認するための注釈行です。
        out_path = os.path.join(save_dir, stem + "_result.png")
# [解説 0069] この行の意図を確認するための注釈行です。
        ok, buf = cv2.imencode(".png", img_bgr)
# [解説 0070] この行の意図を確認するための注釈行です。
        if not ok: return None
# [解説 0071] この行の意図を確認するための注釈行です。
        buf.tofile(out_path)
# [解説 0072] この行の意図を確認するための注釈行です。
        return out_path if os.path.isfile(out_path) else None
# [解説 0073] この行の意図を確認するための注釈行です。
    except Exception:
# [解説 0074] この行の意図を確認するための注釈行です。
        return None
# [解説 0075] この行の意図を確認するための注釈行です。

# [解説 0076] この行の意図を確認するための注釈行です。
def list_basler_devices():
# [解説 0077] この行の意図を確認するための注釈行です。
    if not HAS_PYLYON:
# [解説 0078] この行の意図を確認するための注釈行です。
        return []
# [解説 0079] この行の意図を確認するための注釈行です。
    try:
# [解説 0080] この行の意図を確認するための注釈行です。
        tlf=pylon.TlFactory.GetInstance()
# [解説 0081] この行の意図を確認するための注釈行です。
        devs=tlf.EnumerateDevices()
# [解説 0082] この行の意図を確認するための注釈行です。
        results=[]
# [解説 0083] この行の意図を確認するための注釈行です。
        for idx, dev in enumerate(devs):
# [解説 0084] この行の意図を確認するための注釈行です。
            try:
# [解説 0085] この行の意図を確認するための注釈行です。
                model=dev.GetModelName()
# [解説 0086] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 0087] この行の意図を確認するための注釈行です。
                model="Unknown"
# [解説 0088] この行の意図を確認するための注釈行です。
            try:
# [解説 0089] この行の意図を確認するための注釈行です。
                serial=dev.GetSerialNumber()
# [解説 0090] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 0091] この行の意図を確認するための注釈行です。
                serial=""
# [解説 0092] この行の意図を確認するための注釈行です。
            label=f"{idx}: {model}" + (f" ({serial})" if serial else "")
# [解説 0093] この行の意図を確認するための注釈行です。
            results.append((idx, label))
# [解説 0094] この行の意図を確認するための注釈行です。
        return results
# [解説 0095] この行の意図を確認するための注釈行です。
    except Exception:
# [解説 0096] この行の意図を確認するための注釈行です。
        return []
# [解説 0097] この行の意図を確認するための注釈行です。

# [解説 0098] この行の意図を確認するための注釈行です。

# [解説 0099] この行の意図を確認するための注釈行です。
# ================== 画像処理（直線近似のみ） ==================
# [解説 0100] この行の意図を確認するための注釈行です。
def _fit_line_L2(points_xy):
# [解説 0101] この行の意図を確認するための注釈行です。
    pts = points_xy.astype(np.float32).reshape(-1,1,2)
# [解説 0102] この行の意図を確認するための注釈行です。
    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
# [解説 0103] この行の意図を確認するための注釈行です。
    return float(vx), float(vy), float(x0), float(y0)
# [解説 0104] この行の意図を確認するための注釈行です。

# [解説 0105] この行の意図を確認するための注釈行です。
def _line_params_abc(vx, vy, x0, y0):
# [解説 0106] この行の意図を確認するための注釈行です。
    a, b = vy, -vx
# [解説 0107] この行の意図を確認するための注釈行です。
    c = -(a*x0 + b*y0)
# [解説 0108] この行の意図を確認するための注釈行です。
    s = np.hypot(a, b)
# [解説 0109] この行の意図を確認するための注釈行です。
    if s == 0: return 0.0, 0.0, 0.0
# [解説 0110] この行の意図を確認するための注釈行です。
    return a/s, b/s, c/s
# [解説 0111] この行の意図を確認するための注釈行です。

# [解説 0112] この行の意図を確認するための注釈行です。
def _line_angle_deg(vx, vy):
# [解説 0113] この行の意図を確認するための注釈行です。
    return float(np.degrees(np.arctan2(vy, vx)))
# [解説 0114] この行の意図を確認するための注釈行です。

# [解説 0115] この行の意図を確認するための注釈行です。
def _line_intersection(a1,b1,c1, a2,b2,c2):
# [解説 0116] この行の意図を確認するための注釈行です。
    d = a1*b2 - a2*b1
# [解説 0117] この行の意図を確認するための注釈行です。
    if abs(d) < 1e-9: return None
# [解説 0118] この行の意図を確認するための注釈行です。
    x = (b1*c2 - b2*c1)/d
# [解説 0119] この行の意図を確認するための注釈行です。
    y = (c1*a2 - c2*a1)/d
# [解説 0120] この行の意図を確認するための注釈行です。
    return np.array([x,y], np.float32)
# [解説 0121] この行の意図を確認するための注釈行です。

# [解説 0122] この行の意図を確認するための注釈行です。
def _line_endpoints(a, b, c, width, height):
# [解説 0123] この行の意図を確認するための注釈行です。
    pts=[]
# [解説 0124] この行の意図を確認するための注釈行です。
    if abs(b)>1e-9:
# [解説 0125] この行の意図を確認するための注釈行です。
        for X in (0, width-1):
# [解説 0126] この行の意図を確認するための注釈行です。
            Y=int(round(-(a*X+c)/b)); pts.append((X,Y))
# [解説 0127] この行の意図を確認するための注釈行です。
    if abs(a)>1e-9:
# [解説 0128] この行の意図を確認するための注釈行です。
        for Y in (0, height-1):
# [解説 0129] この行の意図を確認するための注釈行です。
            X=int(round(-(b*Y+c)/a)); pts.append((X,Y))
# [解説 0130] この行の意図を確認するための注釈行です。
    pts_in=[p for p in pts if 0<=p[0]<width and 0<=p[1]<height]
# [解説 0131] この行の意図を確認するための注釈行です。
    if len(pts_in)>=2:
# [解説 0132] この行の意図を確認するための注釈行です。
        return pts_in[0], pts_in[1]
# [解説 0133] この行の意図を確認するための注釈行です。
    return None, None
# [解説 0134] この行の意図を確認するための注釈行です。

# [解説 0135] この行の意図を確認するための注釈行です。
def _unit(v):
# [解説 0136] この行の意図を確認するための注釈行です。
    n = np.linalg.norm(v)
# [解説 0137] この行の意図を確認するための注釈行です。
    return v/n if n>1e-9 else v
# [解説 0138] この行の意図を確認するための注釈行です。

# [解説 0139] この行の意図を確認するための注釈行です。
def _clip_polygon_to_image(poly_pts, w, h):
# [解説 0140] この行の意図を確認するための注釈行です。
    def intersection(A,B,edge):
# [解説 0141] この行の意図を確認するための注釈行です。
        Ax,Ay = A; Bx,By = B
# [解説 0142] この行の意図を確認するための注釈行です。
        if edge is left:
# [解説 0143] この行の意図を確認するための注釈行です。
            t=(0-Ax)/(Bx-Ax+1e-12); return np.array([0, Ay+t*(By-Ay)], np.float32)
# [解説 0144] この行の意図を確認するための注釈行です。
        if edge is right:
# [解説 0145] この行の意図を確認するための注釈行です。
            t=((w-1)-Ax)/(Bx-Ax+1e-12); return np.array([w-1, Ay+t*(By-Ay)], np.float32)
# [解説 0146] この行の意図を確認するための注釈行です。
        if edge is top:
# [解説 0147] この行の意図を確認するための注釈行です。
            t=(0-Ay)/(By-Ay+1e-12); return np.array([Ax+t*(Bx-Ax), 0], np.float32)
# [解説 0148] この行の意図を確認するための注釈行です。
        if edge is bottom:
# [解説 0149] この行の意図を確認するための注釈行です。
            t=((h-1)-Ay)/(By-Ay+1e-12); return np.array([Ax+t*(Bx-Ax), h-1], np.float32)
# [解説 0150] この行の意図を確認するための注釈行です。

# [解説 0151] この行の意図を確認するための注釈行です。
    def clip_edge(points, edge):
# [解説 0152] この行の意図を確認するための注釈行です。
        res=[]
# [解説 0153] この行の意図を確認するための注釈行です。
        for i in range(len(points)):
# [解説 0154] この行の意図を確認するための注釈行です。
            A=points[i]; B=points[(i+1)%len(points)]
# [解説 0155] この行の意図を確認するための注釈行です。
            Ain=edge(A); Bin=edge(B)
# [解説 0156] この行の意図を確認するための注釈行です。
            if Ain and Bin: res.append(B)
# [解説 0157] この行の意図を確認するための注釈行です。
            elif Ain and not Bin: res.append(intersection(A,B,edge))
# [解説 0158] この行の意図を確認するための注釈行です。
            elif (not Ain) and Bin: res.append(intersection(A,B,edge)); res.append(B)
# [解説 0159] この行の意図を確認するための注釈行です。
        return res
# [解説 0160] この行の意図を確認するための注釈行です。

# [解説 0161] この行の意図を確認するための注釈行です。
    left   = lambda P: P[0] >= 0
# [解説 0162] この行の意図を確認するための注釈行です。
    right  = lambda P: P[0] <= w-1
# [解説 0163] この行の意図を確認するための注釈行です。
    top    = lambda P: P[1] >= 0
# [解説 0164] この行の意図を確認するための注釈行です。
    bottom = lambda P: P[1] <= h-1
# [解説 0165] この行の意図を確認するための注釈行です。

# [解説 0166] この行の意図を確認するための注釈行です。
    pts=[p.astype(np.float32) for p in poly_pts]
# [解説 0167] この行の意図を確認するための注釈行です。
    for edge in (left,right,top,bottom):
# [解説 0168] この行の意図を確認するための注釈行です。
        if not pts: break
# [解説 0169] この行の意図を確認するための注釈行です。
        pts = clip_edge(pts, edge)
# [解説 0170] この行の意図を確認するための注釈行です。
    return np.array(pts, np.float32) if len(pts)>=3 else np.empty((0,2), np.float32)
# [解説 0171] この行の意図を確認するための注釈行です。

# [解説 0172] この行の意図を確認するための注釈行です。
def _extract_edge_points(mask_real, band, side, exclude_x_px, exclude_y_px, bbox):
# [解説 0173] この行の意図を確認するための注釈行です。
    edges=cv2.Canny(mask_real, 50, 150)
# [解説 0174] この行の意図を確認するための注釈行です。
    y_idx, x_idx = np.where(edges>0)
# [解説 0175] この行の意図を確認するための注釈行です。
    x, y = x_idx.astype(np.int32), y_idx.astype(np.int32)
# [解説 0176] この行の意図を確認するための注釈行です。
    x0, y0, bw, bh = bbox
# [解説 0177] この行の意図を確認するための注釈行です。
    x1 = x0 + bw - 1; y1 = y0 + bh - 1
# [解説 0178] この行の意図を確認するための注釈行です。
    if side=='top':
# [解説 0179] この行の意図を確認するための注釈行です。
        y_min=max(0,y0); y_max=max(0,min(y1, y0+band))
# [解説 0180] この行の意図を確認するための注釈行です。
        sel=(y>=y_min)&(y<=y_max)
# [解説 0181] この行の意図を確認するための注釈行です。
        sel&=(x>=x0+int(exclude_x_px))&(x<=x1-int(exclude_x_px))
# [解説 0182] この行の意図を確認するための注釈行です。
    elif side=='right':
# [解説 0183] この行の意図を確認するための注釈行です。
        x_min=max(0, x1-band)
# [解説 0184] この行の意図を確認するための注釈行です。
        sel=(x>=x_min)&(x<=x1)
# [解説 0185] この行の意図を確認するための注釈行です。
        sel&=(y>=y0+int(exclude_y_px))&(y<=y1-int(exclude_y_px))
# [解説 0186] この行の意図を確認するための注釈行です。
    elif side=='bottom':
# [解説 0187] この行の意図を確認するための注釈行です。
        y_min=max(0, y1-band)
# [解説 0188] この行の意図を確認するための注釈行です。
        sel=(y>=y_min)&(y<=y1)
# [解説 0189] この行の意図を確認するための注釈行です。
        sel&=(x>=x0+int(exclude_x_px))&(x<=x1-int(exclude_x_px))
# [解説 0190] この行の意図を確認するための注釈行です。
    else:
# [解説 0191] この行の意図を確認するための注釈行です。
        raise ValueError("side must be 'top'|'right'|'bottom'")
# [解説 0192] この行の意図を確認するための注釈行です。
    xs=x[sel].astype(np.float32); ys=y[sel].astype(np.float32)
# [解説 0193] この行の意図を確認するための注釈行です。
    if xs.size<50: return np.empty((0,2), np.float32)
# [解説 0194] この行の意図を確認するための注釈行です。
    return np.stack([xs,ys], axis=1)
# [解説 0195] この行の意図を確認するための注釈行です。

# [解説 0196] この行の意図を確認するための注釈行です。
def _make_corner_quad_from_lines(top_abc, right_abc, trim_x_px, trim_y_px, img_shape):
# [解説 0197] この行の意図を確認するための注釈行です。
    a1,b1,c1=top_abc; a2,b2,c2=right_abc
# [解説 0198] この行の意図を確認するための注釈行です。
    P=_line_intersection(a1,b1,c1, a2,b2,c2)
# [解説 0199] この行の意図を確認するための注釈行です。
    if P is None: return np.empty((0,2), np.float32)
# [解説 0200] この行の意図を確認するための注釈行です。
    t_top=_unit(np.array([-b1,a1],np.float32))
# [解説 0201] この行の意図を確認するための注釈行です。
    t_right=_unit(np.array([-b2,a2],np.float32))
# [解説 0202] この行の意図を確認するための注釈行です。
    if t_top[0]>0: t_top=-t_top
# [解説 0203] この行の意図を確認するための注釈行です。
    if t_right[1]<0: t_right=-t_right
# [解説 0204] この行の意図を確認するための注釈行です。
    p0=P; p1=P+t_right*trim_y_px; p2=p1+t_top*trim_x_px; p3=P+t_top*trim_x_px
# [解説 0205] この行の意図を確認するための注釈行です。
    quad=np.array([p0,p1,p2,p3],np.float32)
# [解説 0206] この行の意図を確認するための注釈行です。
    h,w=img_shape[:2]
# [解説 0207] この行の意図を確認するための注釈行です。
    return _clip_polygon_to_image(quad, w, h)
# [解説 0208] この行の意図を確認するための注釈行です。

# [解説 0209] この行の意図を確認するための注釈行です。
def _make_corner_rd(right_abc, bottom_abc, trim_x_px, trim_y_px, img_shape):
# [解説 0210] この行の意図を確認するための注釈行です。
    aR,bR,cR=right_abc; aB,bB,cB=bottom_abc
# [解説 0211] この行の意図を確認するための注釈行です。
    P=_line_intersection(aR,bR,cR, aB,bB,cB)
# [解説 0212] この行の意図を確認するための注釈行です。
    if P is None: return np.empty((0,2), np.float32)
# [解説 0213] この行の意図を確認するための注釈行です。
    t_bottom=_unit(np.array([-bB,aB],np.float32))
# [解説 0214] この行の意図を確認するための注釈行です。
    t_right =_unit(np.array([-bR,aR],np.float32))
# [解説 0215] この行の意図を確認するための注釈行です。
    if t_bottom[0]>0: t_bottom=-t_bottom
# [解説 0216] この行の意図を確認するための注釈行です。
    if t_right[1]>0:  t_right=-t_right
# [解説 0217] この行の意図を確認するための注釈行です。
    p0=P; p1=P+t_right*trim_y_px; p2=p1+t_bottom*trim_x_px; p3=P+t_bottom*trim_x_px
# [解説 0218] この行の意図を確認するための注釈行です。
    quad=np.array([p0,p1,p2,p3],np.float32)
# [解説 0219] この行の意図を確認するための注釈行です。
    h,w=img_shape[:2]
# [解説 0220] この行の意図を確認するための注釈行です。
    return _clip_polygon_to_image(quad, w, h)
# [解説 0221] この行の意図を確認するための注釈行です。

# [解説 0222] この行の意図を確認するための注釈行です。
def analyze_image(
# [解説 0223] この行の意図を確認するための注釈行です。
    filepath,
# [解説 0224] この行の意図を確認するための注釈行です。
    trim_ratio_x=0.25, trim_ratio_y=0.12, diff_thresh=15000,
# [解説 0225] この行の意図を確認するための注釈行です。
    flip_horizontal=False,
# [解説 0226] この行の意図を確認するための注釈行です。
    band_top=10, band_right=10, band_bottom=10,
# [解説 0227] この行の意図を確認するための注釈行です。
    corner_exclude_x_px=200, corner_exclude_y_px=25
# [解説 0228] この行の意図を確認するための注釈行です。
):
# [解説 0229] この行の意図を確認するための注釈行です。
    img = imread_unicode(filepath)
# [解説 0230] この行の意図を確認するための注釈行です。
    if img is None: raise RuntimeError(f"画像の読み込みに失敗: {filepath}")
# [解説 0231] この行の意図を確認するための注釈行です。
    if flip_horizontal:
# [解説 0232] この行の意図を確認するための注釈行です。
        img=cv2.flip(img, 1)
# [解説 0233] この行の意図を確認するための注釈行です。
    gray=cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# [解説 0234] この行の意図を確認するための注釈行です。
    blur=cv2.GaussianBlur(gray,(5,5),0)
# [解説 0235] この行の意図を確認するための注釈行です。
    _,bin_img=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
# [解説 0236] この行の意図を確認するための注釈行です。
    bin_inv = 255 - bin_img
# [解説 0237] この行の意図を確認するための注釈行です。
    contours,_=cv2.findContours(bin_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
# [解説 0238] この行の意図を確認するための注釈行です。
    if not contours: raise RuntimeError(f"輪郭が検出できません: {filepath}")
# [解説 0239] この行の意図を確認するための注釈行です。
    main_cnt=max(contours, key=cv2.contourArea)
# [解説 0240] この行の意図を確認するための注釈行です。
    mask_real=np.zeros_like(bin_inv); cv2.drawContours(mask_real,[main_cnt],0,255,-1)
# [解説 0241] この行の意図を確認するための注釈行です。

# [解説 0242] この行の意図を確認するための注釈行です。
    rx=np.clip(float(trim_ratio_x),0.0,0.95); ry=np.clip(float(trim_ratio_y),0.0,0.95)
# [解説 0243] この行の意図を確認するための注釈行です。
    x0,y0,bw,bh=cv2.boundingRect(main_cnt)
# [解説 0244] この行の意図を確認するための注釈行です。

# [解説 0245] この行の意図を確認するための注釈行です。
    pts_top   = _extract_edge_points(mask_real, band_top,   'top',    corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
# [解説 0246] この行の意図を確認するための注釈行です。
    pts_bottom= _extract_edge_points(mask_real, band_bottom,'bottom', corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
# [解説 0247] この行の意図を確認するための注釈行です。
    pts_side = _extract_edge_points(mask_real, band_right, 'right', corner_exclude_x_px, corner_exclude_y_px,(x0,y0,bw,bh))
# [解説 0248] この行の意図を確認するための注釈行です。
    if min(pts_top.shape[0], pts_side.shape[0], pts_bottom.shape[0]) < 50:
# [解説 0249] この行の意図を確認するための注釈行です。
        raise RuntimeError("線抽出点が不足しています。band_* や exclude_*、trim比を見直してください。")
# [解説 0250] この行の意図を確認するための注釈行です。

# [解説 0251] この行の意図を確認するための注釈行です。
    vx,vy,xz,yz=_fit_line_L2(pts_top)
# [解説 0252] この行の意図を確認するための注釈行です。
    a_top,b_top,c_top=_line_params_abc(vx,vy,xz,yz)
# [解説 0253] この行の意図を確認するための注釈行です。
    top_angle_deg=_line_angle_deg(vx,vy)
# [解説 0254] この行の意図を確認するための注釈行です。
    top_slope=vy/vx if abs(vx)>1e-9 else float("inf")
# [解説 0255] この行の意図を確認するための注釈行です。
    vx,vy,xz,yz=_fit_line_L2(pts_side)
# [解説 0256] この行の意図を確認するための注釈行です。
    a_side,b_side,c_side=_line_params_abc(vx,vy,xz,yz)
# [解説 0257] この行の意図を確認するための注釈行です。
    side_angle_deg=_line_angle_deg(vx,vy)
# [解説 0258] この行の意図を確認するための注釈行です。
    side_slope=vy/vx if abs(vx)>1e-9 else float("inf")
# [解説 0259] この行の意図を確認するための注釈行です。
    vx,vy,xz,yz=_fit_line_L2(pts_bottom)
# [解説 0260] この行の意図を確認するための注釈行です。
    a_bottom,b_bottom,c_bottom=_line_params_abc(vx,vy,xz,yz)
# [解説 0261] この行の意図を確認するための注釈行です。
    bottom_angle_deg=_line_angle_deg(vx,vy)
# [解説 0262] この行の意図を確認するための注釈行です。
    bottom_slope=vy/vx if abs(vx)>1e-9 else float("inf")
# [解説 0263] この行の意図を確認するための注釈行です。

# [解説 0264] この行の意図を確認するための注釈行です。
    trim_x_px=rx*bw; trim_y_px=ry*bh
# [解説 0265] この行の意図を確認するための注釈行です。
    quad_up=_make_corner_quad_from_lines((a_top,b_top,c_top),(a_side,b_side,c_side), trim_x_px,trim_y_px,img.shape)
# [解説 0266] この行の意図を確認するための注釈行です。
    quad_down=_make_corner_rd((a_side,b_side,c_side),(a_bottom,b_bottom,c_bottom), trim_x_px,trim_y_px,img.shape)
# [解説 0267] この行の意図を確認するための注釈行です。

# [解説 0268] この行の意図を確認するための注釈行です。
    mask_rect=np.zeros_like(bin_inv)
# [解説 0269] この行の意図を確認するための注釈行です。
    if quad_up.shape[0]>=3: cv2.fillPoly(mask_rect,[quad_up.astype(np.int32)],255)
# [解説 0270] この行の意図を確認するための注釈行です。
    if quad_down.shape[0]>=3: cv2.fillPoly(mask_rect,[quad_down.astype(np.int32)],255)
# [解説 0271] この行の意図を確認するための注釈行です。
    mask_diff=cv2.subtract(mask_rect, mask_real)
# [解説 0272] この行の意図を確認するための注釈行です。

# [解説 0273] この行の意図を確認するための注釈行です。
    def _area_quad(mask, quad):
# [解説 0274] この行の意図を確認するための注釈行です。
        if quad.shape[0]<3: return 0, np.zeros_like(mask)
# [解説 0275] この行の意図を確認するための注釈行です。
        roi=np.zeros_like(mask); cv2.fillPoly(roi,[quad.astype(np.int32)],255)
# [解説 0276] この行の意図を確認するための注釈行です。
        area=int(np.sum(cv2.bitwise_and(mask,roi)>128))
# [解説 0277] この行の意図を確認するための注釈行です。
        return area, roi
# [解説 0278] この行の意図を確認するための注釈行です。

# [解説 0279] この行の意図を確認するための注釈行です。
    ru_area, ru_mask = _area_quad(mask_diff, quad_up)
# [解説 0280] この行の意図を確認するための注釈行です。
    rd_area, rd_mask = _area_quad(mask_diff, quad_down)
# [解説 0281] この行の意図を確認するための注釈行です。
    ru_result = "NOTCH" if ru_area>diff_thresh else "NO NOTCH"
# [解説 0282] この行の意図を確認するための注釈行です。
    rd_result = "NOTCH" if rd_area>diff_thresh else "NO NOTCH"
# [解説 0283] この行の意図を確認するための注釈行です。

# [解説 0284] この行の意図を確認するための注釈行です。
    vis=img.copy()
# [解説 0285] この行の意図を確認するための注釈行です。
    def _draw_line(img,a,b,c,color):
# [解説 0286] この行の意図を確認するための注釈行です。
        hh,ww=img.shape[:2]; pts=[]
# [解説 0287] この行の意図を確認するための注釈行です。
        if abs(b)>1e-9:
# [解説 0288] この行の意図を確認するための注釈行です。
            for X in (0,ww-1):
# [解説 0289] この行の意図を確認するための注釈行です。
                Y=int(round(-(a*X+c)/b)); pts.append((X,Y))
# [解説 0290] この行の意図を確認するための注釈行です。
        if abs(a)>1e-9:
# [解説 0291] この行の意図を確認するための注釈行です。
            for Y in (0,hh-1):
# [解説 0292] この行の意図を確認するための注釈行です。
                X=int(round(-(b*Y+c)/a)); pts.append((X,Y))
# [解説 0293] この行の意図を確認するための注釈行です。
        pts_in=[p for p in pts if 0<=p[0]<ww and 0<=p[1]<hh]
# [解説 0294] この行の意図を確認するための注釈行です。
        if len(pts_in)>=2: cv2.line(img, pts_in[0], pts_in[1], color, 2, cv2.LINE_AA)
# [解説 0295] この行の意図を確認するための注釈行です。

# [解説 0296] この行の意図を確認するための注釈行です。
    hh, ww = img.shape[:2]
# [解説 0297] この行の意図を確認するための注釈行です。
    top_p1, top_p2 = _line_endpoints(a_top, b_top, c_top, ww, hh)
# [解説 0298] この行の意図を確認するための注釈行です。
    side_p1, side_p2 = _line_endpoints(a_side, b_side, c_side, ww, hh)
# [解説 0299] この行の意図を確認するための注釈行です。
    bottom_p1, bottom_p2 = _line_endpoints(a_bottom, b_bottom, c_bottom, ww, hh)
# [解説 0300] この行の意図を確認するための注釈行です。

# [解説 0301] この行の意図を確認するための注釈行です。
    _draw_line(vis, a_top,b_top,c_top,         (0,255,0))
# [解説 0302] この行の意図を確認するための注釈行です。
    _draw_line(vis, a_side,b_side,c_side,      (255,0,255))
# [解説 0303] この行の意図を確認するための注釈行です。
    _draw_line(vis, a_bottom,b_bottom,c_bottom,(0,255,255))
# [解説 0304] この行の意図を確認するための注釈行です。

# [解説 0305] この行の意図を確認するための注釈行です。
    vis_mask=vis.copy()
# [解説 0306] この行の意図を確認するための注釈行です。
    vis_mask[mask_diff>128]=[0,255,255]
# [解説 0307] この行の意図を確認するための注釈行です。
    if quad_up.shape[0]>=3: cv2.polylines(vis_mask,[quad_up.astype(np.int32)],True,(0,0,255),3)
# [解説 0308] この行の意図を確認するための注釈行です。
    if quad_down.shape[0]>=3: cv2.polylines(vis_mask,[quad_down.astype(np.int32)],True,(255,0,0),3)
# [解説 0309] この行の意図を確認するための注釈行です。

# [解説 0310] この行の意図を確認するための注釈行です。
    if quad_up.shape[0]>=3:
# [解説 0311] この行の意図を確認するための注釈行です。
        P=np.mean(quad_up, axis=0).astype(int)
# [解説 0312] この行の意図を確認するための注釈行です。
        cv2.putText(vis_mask, f"RU: {ru_result} ({ru_area})",(P[0]+5,P[1]+5),cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,0,255),3)
# [解説 0313] この行の意図を確認するための注釈行です。
    if quad_down.shape[0]>=3:
# [解説 0314] この行の意図を確認するための注釈行です。
        P=np.mean(quad_down, axis=0).astype(int)
# [解説 0315] この行の意図を確認するための注釈行です。
        cv2.putText(vis_mask, f"RD: {rd_result} ({rd_area})",(P[0]+5,P[1]+5),cv2.FONT_HERSHEY_SIMPLEX,1.1,(255,0,0),3)
# [解説 0316] この行の意図を確認するための注釈行です。

# [解説 0317] この行の意図を確認するための注釈行です。
    if flip_horizontal:
# [解説 0318] この行の意図を確認するための注釈行です。
        cv2.putText(vis_mask, "FLIP: ON", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3, cv2.LINE_AA)
# [解説 0319] この行の意図を確認するための注釈行です。
        cv2.putText(vis_mask, "FLIP: ON", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30,30,30), 1, cv2.LINE_AA)
# [解説 0320] この行の意図を確認するための注釈行です。

# [解説 0321] この行の意図を確認するための注釈行です。
    side_label = "Side"
# [解説 0322] この行の意図を確認するための注釈行です。
    return {
# [解説 0323] この行の意図を確認するための注釈行です。
        "img_bgr": vis_mask,
# [解説 0324] この行の意図を確認するための注釈行です。
        "ru_area": ru_area, "rd_area": rd_area,
# [解説 0325] この行の意図を確認するための注釈行です。
        "ru_result": ru_result, "rd_result": rd_result,
# [解説 0326] この行の意図を確認するための注釈行です。
        "mask_diff": mask_diff, "ru_roi_mask": ru_mask, "rd_roi_mask": rd_mask,
# [解説 0327] この行の意図を確認するための注釈行です。
        "top_angle_deg": top_angle_deg, "side_angle_deg": side_angle_deg,
# [解説 0328] この行の意図を確認するための注釈行です。
        "bottom_angle_deg": bottom_angle_deg, "top_slope": top_slope,
# [解説 0329] この行の意図を確認するための注釈行です。
        "side_slope": side_slope, "bottom_slope": bottom_slope,
# [解説 0330] この行の意図を確認するための注釈行です。
        "side_label": side_label,
# [解説 0331] この行の意図を確認するための注釈行です。
        "top_line": (top_p1, top_p2),
# [解説 0332] この行の意図を確認するための注釈行です。
        "side_line": (side_p1, side_p2),
# [解説 0333] この行の意図を確認するための注釈行です。
        "bottom_line": (bottom_p1, bottom_p2)
# [解説 0334] この行の意図を確認するための注釈行です。
    }
# [解説 0335] この行の意図を確認するための注釈行です。

# [解説 0336] この行の意図を確認するための注釈行です。

# [解説 0337] この行の意図を確認するための注釈行です。
# ================== デバイス薄ラッパ ==================
# [解説 0338] この行の意図を確認するための注釈行です。
class BaslerCamera:
# [解説 0339] この行の意図を確認するための注釈行です。
    def __init__(self, device_index=0, timeout_ms=3000):
# [解説 0340] この行の意図を確認するための注釈行です。
        self.device_index=device_index
# [解説 0341] この行の意図を確認するための注釈行です。
        self.timeout_ms=timeout_ms
# [解説 0342] この行の意図を確認するための注釈行です。
        self.cam=None; self.converter=None
# [解説 0343] この行の意図を確認するための注釈行です。

# [解説 0344] この行の意図を確認するための注釈行です。
    def open(self):
# [解説 0345] この行の意図を確認するための注釈行です。
        if not HAS_PYLYON: raise RuntimeError("pypylon 未導入")
# [解説 0346] この行の意図を確認するための注釈行です。
        tlf=pylon.TlFactory.GetInstance()
# [解説 0347] この行の意図を確認するための注釈行です。
        devs=tlf.EnumerateDevices()
# [解説 0348] この行の意図を確認するための注釈行です。
        if not devs: raise RuntimeError("Basler カメラが見つかりません")
# [解説 0349] この行の意図を確認するための注釈行です。
        idx=min(max(0,self.device_index), len(devs)-1)
# [解説 0350] この行の意図を確認するための注釈行です。
        self.cam=pylon.InstantCamera(tlf.CreateDevice(devs[idx]))
# [解説 0351] この行の意図を確認するための注釈行です。
        self.cam.Open()
# [解説 0352] この行の意図を確認するための注釈行です。
        self.converter=pylon.ImageFormatConverter()
# [解説 0353] この行の意図を確認するための注釈行です。
        self.converter.OutputPixelFormat=pylon.PixelType_BGR8packed
# [解説 0354] この行の意図を確認するための注釈行です。
        self.converter.OutputBitAlignment=pylon.OutputBitAlignment_MsbAligned
# [解説 0355] この行の意図を確認するための注釈行です。
        try:
# [解説 0356] この行の意図を確認するための注釈行です。
            self.cam.ExposureAuto.SetValue("Off")
# [解説 0357] この行の意図を確認するための注釈行です。
            self.cam.GainAuto.SetValue("Off")
# [解説 0358] この行の意図を確認するための注釈行です。
            self.cam.TriggerSelector.SetValue("FrameStart")
# [解説 0359] この行の意図を確認するための注釈行です。
            self.cam.TriggerMode.SetValue("On")
# [解説 0360] この行の意図を確認するための注釈行です。
            self.cam.TriggerSource.SetValue("Software")
# [解説 0361] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0362] この行の意図を確認するための注釈行です。
            pass
# [解説 0363] この行の意図を確認するための注釈行です。
        self._start_grabbing_if_needed()
# [解説 0364] この行の意図を確認するための注釈行です。

# [解説 0365] この行の意図を確認するための注釈行です。
    def _start_grabbing_if_needed(self):
# [解説 0366] この行の意図を確認するための注釈行です。
        if self.cam and (not self.cam.IsGrabbing()):
# [解説 0367] この行の意図を確認するための注釈行です。
            self.cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
# [解説 0368] この行の意図を確認するための注釈行です。

# [解説 0369] この行の意図を確認するための注釈行です。
    def is_open(self):
# [解説 0370] この行の意図を確認するための注釈行です。
        return bool(self.cam and self.cam.IsOpen())
# [解説 0371] この行の意図を確認するための注釈行です。

# [解説 0372] この行の意図を確認するための注釈行です。
    def is_healthy(self):
# [解説 0373] この行の意図を確認するための注釈行です。
        return self.is_open()
# [解説 0374] この行の意図を確認するための注釈行です。

# [解説 0375] この行の意図を確認するための注釈行です。
    def reopen(self):
# [解説 0376] この行の意図を確認するための注釈行です。
        self.close()
# [解説 0377] この行の意図を確認するための注釈行です。
        self.open()
# [解説 0378] この行の意図を確認するための注釈行です。

# [解説 0379] この行の意図を確認するための注釈行です。
    def close(self):
# [解説 0380] この行の意図を確認するための注釈行です。
        try:
# [解説 0381] この行の意図を確認するための注釈行です。
            if self.cam:
# [解説 0382] この行の意図を確認するための注釈行です。
                if self.cam.IsGrabbing(): self.cam.StopGrabbing()
# [解説 0383] この行の意図を確認するための注釈行です。
                if self.cam.IsOpen(): self.cam.Close()
# [解説 0384] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0385] この行の意図を確認するための注釈行です。
            pass
# [解説 0386] この行の意図を確認するための注釈行です。
        self.cam=None
# [解説 0387] この行の意図を確認するための注釈行です。
        self.converter=None
# [解説 0388] この行の意図を確認するための注釈行です。

# [解説 0389] この行の意図を確認するための注釈行です。
    def snap_bgr(self):
# [解説 0390] この行の意図を確認するための注釈行です。
        if not self.is_open():
# [解説 0391] この行の意図を確認するための注釈行です。
            self.open()
# [解説 0392] この行の意図を確認するための注釈行です。
        self._start_grabbing_if_needed()
# [解説 0393] この行の意図を確認するための注釈行です。
        try:
# [解説 0394] この行の意図を確認するための注釈行です。
            self.cam.TriggerSoftware.Execute()
# [解説 0395] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0396] この行の意図を確認するための注釈行です。
            pass
# [解説 0397] この行の意図を確認するための注釈行です。
        res=self.cam.RetrieveResult(self.timeout_ms, pylon.TimeoutHandling_Return)
# [解説 0398] この行の意図を確認するための注釈行です。
        if res is None or not res.GrabSucceeded():
# [解説 0399] この行の意図を確認するための注釈行です。
            if res is not None: res.Release()
# [解説 0400] この行の意図を確認するための注釈行です。
            raise RuntimeError("画像取得に失敗")
# [解説 0401] この行の意図を確認するための注釈行です。
        try:
# [解説 0402] この行の意図を確認するための注釈行です。
            image=self.converter.Convert(res)
# [解説 0403] この行の意図を確認するための注釈行です。
            img=image.GetArray()
# [解説 0404] この行の意図を確認するための注釈行です。
            return img
# [解説 0405] この行の意図を確認するための注釈行です。
        finally:
# [解説 0406] この行の意図を確認するための注釈行です。
            res.Release()
# [解説 0407] この行の意図を確認するための注釈行です。

# [解説 0408] この行の意図を確認するための注釈行です。
    def __del__(self):
# [解説 0409] この行の意図を確認するための注釈行です。
        self.close()
# [解説 0410] この行の意図を確認するための注釈行です。

# [解説 0411] この行の意図を確認するための注釈行です。

# [解説 0412] この行の意図を確認するための注釈行です。
class PLCClient:
# [解説 0413] この行の意図を確認するための注釈行です。
    def __init__(self):
# [解説 0414] この行の意図を確認するための注釈行です。
        self.cli=None
# [解説 0415] この行の意図を確認するための注釈行です。

# [解説 0416] この行の意図を確認するための注釈行です。
    def connect(self, host:str, port:int):
# [解説 0417] この行の意図を確認するための注釈行です。
        if not HAS_PYMC: raise RuntimeError("pymcprotocol 未導入")
# [解説 0418] この行の意図を確認するための注釈行です。
        self.cli=pymcprotocol.Type3E(plctype="Q")
# [解説 0419] この行の意図を確認するための注釈行です。
        self.cli.connect(host, port)
# [解説 0420] この行の意図を確認するための注釈行です。

# [解説 0421] この行の意図を確認するための注釈行です。
    def close(self):
# [解説 0422] この行の意図を確認するための注釈行です。
        try:
# [解説 0423] この行の意図を確認するための注釈行です。
            if self.cli: self.cli.close()
# [解説 0424] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0425] この行の意図を確認するための注釈行です。
            pass
# [解説 0426] この行の意図を確認するための注釈行です。
        self.cli=None
# [解説 0427] この行の意図を確認するための注釈行です。

# [解説 0428] この行の意図を確認するための注釈行です。
    def read_bit(self, head:str)->bool:
# [解説 0429] この行の意図を確認するための注釈行です。
        vals=self.cli.batchread_bitunits(headdevice=head, readsize=1)
# [解説 0430] この行の意図を確認するための注釈行です。
        v=int(vals[0]) if isinstance(vals,(list,tuple)) else int(vals)
# [解説 0431] この行の意図を確認するための注釈行です。
        return bool(v)
# [解説 0432] この行の意図を確認するための注釈行です。

# [解説 0433] この行の意図を確認するための注釈行です。
    def write_bit(self, head:str, value:bool):
# [解説 0434] この行の意図を確認するための注釈行です。
        self.cli.batchwrite_bitunits(headdevice=head, values=[1 if value else 0])
# [解説 0435] この行の意図を確認するための注釈行です。

# [解説 0436] この行の意図を確認するための注釈行です。
    def pulse_bit(self, head:str, ms:int=50):
# [解説 0437] この行の意図を確認するための注釈行です。
        self.write_bit(head, True)
# [解説 0438] この行の意図を確認するための注釈行です。
        time.sleep(max(0,ms)/1000.0)
# [解説 0439] この行の意図を確認するための注釈行です。
        self.write_bit(head, False)
# [解説 0440] この行の意図を確認するための注釈行です。

# [解説 0441] この行の意図を確認するための注釈行です。
    def read_word(self, head:str)->int:
# [解説 0442] この行の意図を確認するための注釈行です。
        vals=self.cli.batchread_wordunits(headdevice=head, readsize=1)
# [解説 0443] この行の意図を確認するための注釈行です。
        v=int(vals[0]) if isinstance(vals,(list,tuple)) else int(vals)
# [解説 0444] この行の意図を確認するための注釈行です。
        return v & 0xFFFF
# [解説 0445] この行の意図を確認するための注釈行です。

# [解説 0446] この行の意図を確認するための注釈行です。
    def write_word(self, head:str, value:int):
# [解説 0447] この行の意図を確認するための注釈行です。
        self.cli.batchwrite_wordunits(headdevice=head, values=[int(value)&0xFFFF])
# [解説 0448] この行の意図を確認するための注釈行です。

# [解説 0449] この行の意図を確認するための注釈行です。

# [解説 0450] この行の意図を確認するための注釈行です。
# ================== 設定 永続化 ==================
# [解説 0451] この行の意図を確認するための注釈行です。
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".notch_app_config.json")
# [解説 0452] この行の意図を確認するための注釈行です。

# [解説 0453] この行の意図を確認するための注釈行です。
@dataclass
# [解説 0454] この行の意図を確認するための注釈行です。
class AppConfig:
# [解説 0455] この行の意図を確認するための注釈行です。
    # 解析パラメータ
# [解説 0456] この行の意図を確認するための注釈行です。
    trim_ratio_x: float = 0.25
# [解説 0457] この行の意図を確認するための注釈行です。
    trim_ratio_y: float = 0.12
# [解説 0458] この行の意図を確認するための注釈行です。
    diff_thresh: int   = 15000
# [解説 0459] この行の意図を確認するための注釈行です。
    band_top: int = 10
# [解説 0460] この行の意図を確認するための注釈行です。
    band_right: int = 10
# [解説 0461] この行の意図を確認するための注釈行です。
    band_bottom:int = 10
# [解説 0462] この行の意図を確認するための注釈行です。
    corner_exclude_x_px:int = 200
# [解説 0463] この行の意図を確認するための注釈行です。
    corner_exclude_y_px:int = 25
# [解説 0464] この行の意図を確認するための注釈行です。
    auto_preview: bool = True
# [解説 0465] この行の意図を確認するための注釈行です。
    flip_horizontal: bool = False
# [解説 0466] この行の意図を確認するための注釈行です。

# [解説 0467] この行の意図を確認するための注釈行です。
    # 出力
# [解説 0468] この行の意図を確認するための注釈行です。
    output_dir: str = ""
# [解説 0469] この行の意図を確認するための注釈行です。

# [解説 0470] この行の意図を確認するための注釈行です。
    # カメラ設定
# [解説 0471] この行の意図を確認するための注釈行です。
    camera_index: int = 0
# [解説 0472] この行の意図を確認するための注釈行です。

# [解説 0473] この行の意図を確認するための注釈行です。
    # PLC 設定（メニューバーから編集）
# [解説 0474] この行の意図を確認するための注釈行です。
    plc_ip: str = "192.168.1.2"
# [解説 0475] この行の意図を確認するための注釈行です。
    plc_port: int = 1026
# [解説 0476] この行の意図を確認するための注釈行です。
    dev_trig: str = "M100"
# [解説 0477] この行の意図を確認するための注釈行です。
    dev_ru:   str = "M101"
# [解説 0478] この行の意図を確認するための注釈行です。
    dev_rd:   str = "M102"
# [解説 0479] この行の意図を確認するための注釈行です。
    dev_done: str = "M103"
# [解説 0480] この行の意図を確認するための注釈行です。
    dev_busy: str = "M104"
# [解説 0481] この行の意図を確認するための注釈行です。
    dev_err_to: str = "M105"
# [解説 0482] この行の意図を確認するための注釈行です。
    dev_err_an: str = "M106"
# [解説 0483] この行の意図を確認するための注釈行です。
    done_ms: int = 50
# [解説 0484] この行の意図を確認するための注釈行です。
    use_sw_trig: bool = True
# [解説 0485] この行の意図を確認するための注釈行です。
    timeout_ms: int = 3000
# [解説 0486] この行の意図を確認するための注釈行です。

# [解説 0487] この行の意図を確認するための注釈行です。
    # ハートビート
# [解説 0488] この行の意図を確認するための注釈行です。
    dev_alive: str = "D100"
# [解説 0489] この行の意図を確認するための注釈行です。
    alive_ms: int = 1000
# [解説 0490] この行の意図を確認するための注釈行です。
    alive_step: int = 1
# [解説 0491] この行の意図を確認するための注釈行です。
    alive_auto: bool = False
# [解説 0492] この行の意図を確認するための注釈行です。

# [解説 0493] この行の意図を確認するための注釈行です。
    # 一時ファイル管理
# [解説 0494] この行の意図を確認するための注釈行です。
    temp_max_files: int = 50
# [解説 0495] この行の意図を確認するための注釈行です。
    temp_prefixes: list[str] = field(default_factory=lambda: ["BaslerShot_", "PLCshot_"])
# [解説 0496] この行の意図を確認するための注釈行です。

# [解説 0497] この行の意図を確認するための注釈行です。
    # 結果CSV & PLCショット保存先
# [解説 0498] この行の意図を確認するための注釈行です。
    csv_max_records: int = 1000
# [解説 0499] この行の意図を確認するための注釈行です。
    plc_shot_dir: str = ""  # 空なら tempdir
# [解説 0500] この行の意図を確認するための注釈行です。

# [解説 0501] この行の意図を確認するための注釈行です。
    # 自動再接続/監視
# [解説 0502] この行の意図を確認するための注釈行です。
    auto_reconnect: bool = True
# [解説 0503] この行の意図を確認するための注釈行です。
    auto_watch_on_ready: bool = True
# [解説 0504] この行の意図を確認するための注釈行です。

# [解説 0505] この行の意図を確認するための注釈行です。
    @staticmethod
# [解説 0506] この行の意図を確認するための注釈行です。
    def load():
# [解説 0507] この行の意図を確認するための注釈行です。
        try:
# [解説 0508] この行の意図を確認するための注釈行です。
            with open(CONFIG_PATH,"r",encoding="utf-8") as f:
# [解説 0509] この行の意図を確認するための注釈行です。
                data=json.load(f)
# [解説 0510] この行の意図を確認するための注釈行です。
            allowed = {item.name for item in fields(AppConfig)}
# [解説 0511] この行の意図を確認するための注釈行です。
            cleaned = {k: v for k, v in data.items() if k in allowed}
# [解説 0512] この行の意図を確認するための注釈行です。
            return AppConfig(**cleaned)
# [解説 0513] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0514] この行の意図を確認するための注釈行です。
            return AppConfig()
# [解説 0515] この行の意図を確認するための注釈行です。

# [解説 0516] この行の意図を確認するための注釈行です。
    def save(self):
# [解説 0517] この行の意図を確認するための注釈行です。
        try:
# [解説 0518] この行の意図を確認するための注釈行です。
            with open(CONFIG_PATH,"w",encoding="utf-8") as f:
# [解説 0519] この行の意図を確認するための注釈行です。
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
# [解説 0520] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0521] この行の意図を確認するための注釈行です。
            pass
# [解説 0522] この行の意図を確認するための注釈行です。

# [解説 0523] この行の意図を確認するための注釈行です。

# [解説 0524] この行の意図を確認するための注釈行です。
# ================== UI: ズーム・パンキャンバス ==================
# [解説 0525] この行の意図を確認するための注釈行です。
class ZoomPanCanvas(tk.Canvas):
# [解説 0526] この行の意図を確認するための注釈行です。
    def __init__(self, master, bg="#222", **kw):
# [解説 0527] この行の意図を確認するための注釈行です。
        super().__init__(master, bg=bg, highlightthickness=0, **kw)
# [解説 0528] この行の意図を確認するための注釈行です。
        self._img_pil=None; self._img_tk=None; self._img_id=None
# [解説 0529] この行の意図を確認するための注釈行です。
        self.zoom=1.0; self.min_zoom=0.05; self.max_zoom=10.0
# [解説 0530] この行の意図を確認するための注釈行です。
        self.offset=np.array([0.0,0.0]); self._drag_start=None
# [解説 0531] この行の意図を確認するための注釈行です。
        self.bind("<Configure>", self._on_configure)
# [解説 0532] この行の意図を確認するための注釈行です。
        self.bind("<ButtonPress-1>", self._on_press)
# [解説 0533] この行の意図を確認するための注釈行です。
        self.bind("<B1-Motion>", self._on_drag)
# [解説 0534] この行の意図を確認するための注釈行です。
        self.bind("<ButtonRelease-1>", self._on_release)
# [解説 0535] この行の意図を確認するための注釈行です。
        self.bind("<MouseWheel>", self._on_wheel)
# [解説 0536] この行の意図を確認するための注釈行です。
        self.bind("<Button-4>", lambda e: self._zoom_at(1.1, e.x, e.y))
# [解説 0537] この行の意図を確認するための注釈行です。
        self.bind("<Button-5>", lambda e: self._zoom_at(1/1.1, e.x, e.y))
# [解説 0538] この行の意図を確認するための注釈行です。

# [解説 0539] この行の意図を確認するための注釈行です。
    def set_image(self, pil_image):
# [解説 0540] この行の意図を確認するための注釈行です。
        self._img_pil=pil_image
# [解説 0541] この行の意図を確認するための注釈行です。
        if self._img_id is None: self.fit_to_window()
# [解説 0542] この行の意図を確認するための注釈行です。
        else: self._render()
# [解説 0543] この行の意図を確認するための注釈行です。

# [解説 0544] この行の意図を確認するための注釈行です。
    def clear(self):
# [解説 0545] この行の意図を確認するための注釈行です。
        if self._img_id is not None: self.delete(self._img_id); self._img_id=None
# [解説 0546] この行の意図を確認するための注釈行です。
        self._img_pil=None; self._img_tk=None; self.zoom=1.0; self.offset=np.array([0.0,0.0])
# [解説 0547] この行の意図を確認するための注釈行です。

# [解説 0548] この行の意図を確認するための注釈行です。
    def fit_to_window(self):
# [解説 0549] この行の意図を確認するための注釈行です。
        if self._img_pil is None: return
# [解説 0550] この行の意図を確認するための注釈行です。
        cw=max(self.winfo_width(),1); ch=max(self.winfo_height(),1)
# [解説 0551] この行の意図を確認するための注釈行です。
        iw,ih=self._img_pil.size
# [解説 0552] この行の意図を確認するための注釈行です。
        scale=min(cw/iw, ch/ih) if iw and ih else 1.0
# [解説 0553] この行の意図を確認するための注釈行です。
        scale=max(self.min_zoom, min(self.max_zoom, scale))
# [解説 0554] この行の意図を確認するための注釈行です。
        self.zoom=scale
# [解説 0555] この行の意図を確認するための注釈行です。
        self.offset=np.array([(cw - iw*self.zoom)/2.0, (ch - ih*self.zoom)/2.0])
# [解説 0556] この行の意図を確認するための注釈行です。
        self._render()
# [解説 0557] この行の意図を確認するための注釈行です。

# [解説 0558] この行の意図を確認するための注釈行です。
    def set_zoom_100(self):
# [解説 0559] この行の意図を確認するための注釈行です。
        if self._img_pil is None: return
# [解説 0560] この行の意図を確認するための注釈行です。
        cw=max(self.winfo_width(),1); ch=max(self.winfo_height(),1)
# [解説 0561] この行の意図を確認するための注釈行です。
        iw,ih=self._img_pil.size
# [解説 0562] この行の意図を確認するための注釈行です。
        self.zoom=1.0
# [解説 0563] この行の意図を確認するための注釈行です。
        self.offset=np.array([(cw-iw)/2.0, (ch-ih)/2.0]); self._render()
# [解説 0564] この行の意図を確認するための注釈行です。

# [解説 0565] この行の意図を確認するための注釈行です。
    def zoom_in(self):  self._zoom_at(1.2, self.winfo_width()/2.0, self.winfo_height()/2.0)
# [解説 0566] この行の意図を確認するための注釈行です。
    def zoom_out(self): self._zoom_at(1/1.2, self.winfo_width()/2.0, self.winfo_height()/2.0)
# [解説 0567] この行の意図を確認するための注釈行です。

# [解説 0568] この行の意図を確認するための注釈行です。
    def _on_configure(self,_): self._render()
# [解説 0569] この行の意図を確認するための注釈行です。
    def _on_press(self,e): self._drag_start=np.array([e.x,e.y])
# [解説 0570] この行の意図を確認するための注釈行です。
    def _on_drag(self,e):
# [解説 0571] この行の意図を確認するための注釈行です。
        if self._drag_start is None: return
# [解説 0572] この行の意図を確認するための注釈行です。
        cur=np.array([e.x,e.y]); delta=cur-self._drag_start
# [解説 0573] この行の意図を確認するための注釈行です。
        self._drag_start=cur; self.offset+=delta; self._render()
# [解説 0574] この行の意図を確認するための注釈行です。
    def _on_release(self,_): self._drag_start=None
# [解説 0575] この行の意図を確認するための注釈行です。
    def _on_wheel(self,e):
# [解説 0576] この行の意図を確認するための注釈行です。
        if e.delta>0: self._zoom_at(1.1, e.x, e.y)
# [解説 0577] この行の意図を確認するための注釈行です。
        elif e.delta<0: self._zoom_at(1/1.1, e.x, e.y)
# [解説 0578] この行の意図を確認するための注釈行です。
    def _zoom_at(self, factor, cx, cy):
# [解説 0579] この行の意図を確認するための注釈行です。
        if self._img_pil is None: return
# [解説 0580] この行の意図を確認するための注釈行です。
        old=self.zoom; new=max(self.min_zoom, min(self.max_zoom, self.zoom*factor))
# [解説 0581] この行の意図を確認するための注釈行です。
        if abs(new-old)<1e-6: return
# [解説 0582] この行の意図を確認するための注釈行です。
        img_pt=(np.array([cx,cy]) - self.offset)/old
# [解説 0583] この行の意図を確認するための注釈行です。
        self.zoom=new; self.offset=np.array([cx,cy]) - img_pt*self.zoom
# [解説 0584] この行の意図を確認するための注釈行です。
        self._render()
# [解説 0585] この行の意図を確認するための注釈行です。
    def _render(self):
# [解説 0586] この行の意図を確認するための注釈行です。
        self.delete("all")
# [解説 0587] この行の意図を確認するための注釈行です。
        if self._img_pil is None: return
# [解説 0588] この行の意図を確認するための注釈行です。
        iw,ih=self._img_pil.size
# [解説 0589] この行の意図を確認するための注釈行です。
        disp=self._img_pil.resize((max(1,int(iw*self.zoom)), max(1,int(ih*self.zoom))), Image.LANCZOS)
# [解説 0590] この行の意図を確認するための注釈行です。
        self._img_tk=ImageTk.PhotoImage(disp)
# [解説 0591] この行の意図を確認するための注釈行です。
        self._img_id=self.create_image(self.offset[0], self.offset[1], image=self._img_tk, anchor="nw")
# [解説 0592] この行の意図を確認するための注釈行です。

# [解説 0593] この行の意図を確認するための注釈行です。

# [解説 0594] この行の意図を確認するための注釈行です。
# ================== スクロール可能フレーム（左ペイン） ==================
# [解説 0595] この行の意図を確認するための注釈行です。
class ScrollFrame(ttk.Frame):
# [解説 0596] この行の意図を確認するための注釈行です。
    def __init__(self, master, **kw):
# [解説 0597] この行の意図を確認するための注釈行です。
        super().__init__(master, **kw)
# [解説 0598] この行の意図を確認するための注釈行です。
        canvas = tk.Canvas(self, highlightthickness=0)
# [解説 0599] この行の意図を確認するための注釈行です。
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
# [解説 0600] この行の意図を確認するための注釈行です。
        canvas.configure(yscrollcommand=vbar.set)
# [解説 0601] この行の意図を確認するための注釈行です。
        canvas.grid(row=0,column=0,sticky="nsew")
# [解説 0602] この行の意図を確認するための注釈行です。
        vbar.grid(row=0,column=1,sticky="ns")
# [解説 0603] この行の意図を確認するための注釈行です。
        self.columnconfigure(0,weight=1); self.rowconfigure(0,weight=1)
# [解説 0604] この行の意図を確認するための注釈行です。

# [解説 0605] この行の意図を確認するための注釈行です。
        self.inner = ttk.Frame(canvas)
# [解説 0606] この行の意図を確認するための注釈行です。
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
# [解説 0607] この行の意図を確認するための注釈行です。
        self._win = canvas.create_window((0,0), window=self.inner, anchor="nw")
# [解説 0608] この行の意図を確認するための注釈行です。
        def _resize(_):
# [解説 0609] この行の意図を確認するための注釈行です。
            canvas.itemconfigure(self._win, width=canvas.winfo_width())
# [解説 0610] この行の意図を確認するための注釈行です。
        canvas.bind("<Configure>", _resize)
# [解説 0611] この行の意図を確認するための注釈行です。

# [解説 0612] この行の意図を確認するための注釈行です。

# [解説 0613] この行の意図を確認するための注釈行です。
# ================== メインアプリ ==================
# [解説 0614] この行の意図を確認するための注釈行です。
class NotchApp(ttk.Window):
# [解説 0615] この行の意図を確認するための注釈行です。
    def __init__(self):
# [解説 0616] この行の意図を確認するための注釈行です。
        super().__init__(themename="darkly")
# [解説 0617] この行の意図を確認するための注釈行です。
        self.title("ガラス基板ノッチ判定ツール")
# [解説 0618] この行の意図を確認するための注釈行です。
        self.geometry("1500x1000")
# [解説 0619] この行の意図を確認するための注釈行です。
        self.minsize(1100, 760)
# [解説 0620] この行の意図を確認するための注釈行です。

# [解説 0621] この行の意図を確認するための注釈行です。
        # 状態
# [解説 0622] この行の意図を確認するための注釈行です。
        self.cfg = AppConfig.load()
# [解説 0623] この行の意図を確認するための注釈行です。
        self._trace_lock=False
# [解説 0624] この行の意図を確認するための注釈行です。
        self.file_paths=[]
# [解説 0625] この行の意図を確認するための注釈行です。
        self.output_dir=self.cfg.output_dir
# [解説 0626] この行の意図を確認するための注釈行です。
        self.last_sel_index=None
# [解説 0627] この行の意図を確認するための注釈行です。
        self.basler=None
# [解説 0628] この行の意図を確認するための注釈行です。
        self.last_result=None; self.last_result_path=None
# [解説 0629] この行の意図を確認するための注釈行です。

# [解説 0630] この行の意図を確認するための注釈行です。
        # カメラ排他ロック
# [解説 0631] この行の意図を確認するための注釈行です。
        self._cam_lock = threading.RLock()
# [解説 0632] この行の意図を確認するための注釈行です。

# [解説 0633] この行の意図を確認するための注釈行です。
        # 自動プレビュー用 after ジョブID
# [解説 0634] この行の意図を確認するための注釈行です。
        self._preview_job = None
# [解説 0635] この行の意図を確認するための注釈行です。

# [解説 0636] この行の意図を確認するための注釈行です。
        # 解析パラメータ（Tk変数）
# [解説 0637] この行の意図を確認するための注釈行です。
        self.trim_ratio_x=tk.DoubleVar(value=self.cfg.trim_ratio_x)
# [解説 0638] この行の意図を確認するための注釈行です。
        self.trim_ratio_y=tk.DoubleVar(value=self.cfg.trim_ratio_y)
# [解説 0639] この行の意図を確認するための注釈行です。
        self.diff_thresh = tk.IntVar(value=self.cfg.diff_thresh)
# [解説 0640] この行の意図を確認するための注釈行です。
        self.band_top=tk.IntVar(value=self.cfg.band_top)
# [解説 0641] この行の意図を確認するための注釈行です。
        self.band_right=tk.IntVar(value=self.cfg.band_right)
# [解説 0642] この行の意図を確認するための注釈行です。
        self.band_bottom=tk.IntVar(value=self.cfg.band_bottom)
# [解説 0643] この行の意図を確認するための注釈行です。
        self.corner_exclude_x_px=tk.IntVar(value=self.cfg.corner_exclude_x_px)
# [解説 0644] この行の意図を確認するための注釈行です。
        self.corner_exclude_y_px=tk.IntVar(value=self.cfg.corner_exclude_y_px)
# [解説 0645] この行の意図を確認するための注釈行です。
        self.auto_preview=tk.BooleanVar(value=self.cfg.auto_preview)
# [解説 0646] この行の意図を確認するための注釈行です。
        self.flip_horizontal=tk.BooleanVar(value=self.cfg.flip_horizontal)
# [解説 0647] この行の意図を確認するための注釈行です。
        self.var_camera_index=tk.IntVar(value=self.cfg.camera_index)
# [解説 0648] この行の意図を確認するための注釈行です。

# [解説 0649] この行の意図を確認するための注釈行です。
        # PLC/カメラ/ハートビート用
# [解説 0650] この行の意図を確認するための注釈行です。
        self.plc=PLCClient()
# [解説 0651] この行の意図を確認するための注釈行です。
        self.plc_connected=False
# [解説 0652] この行の意図を確認するための注釈行です。
        self.plc_thread=None; self.plc_stop=False; self.prev_trig=False
# [解説 0653] この行の意図を確認するための注釈行です。
        self.var_use_sw_trig=tk.BooleanVar(value=self.cfg.use_sw_trig)
# [解説 0654] この行の意図を確認するための注釈行です。
        self.var_timeout_ms=tk.IntVar(value=self.cfg.timeout_ms)
# [解説 0655] この行の意図を確認するための注釈行です。
        self.var_done_ms=tk.IntVar(value=self.cfg.done_ms)
# [解説 0656] この行の意図を確認するための注釈行です。

# [解説 0657] この行の意図を確認するための注釈行です。
        # アドレスやIP（メニュー側で編集）
# [解説 0658] この行の意図を確認するための注釈行です。
        self.var_plc_ip=tk.StringVar(value=self.cfg.plc_ip)
# [解説 0659] この行の意図を確認するための注釈行です。
        self.var_plc_port=tk.IntVar(value=self.cfg.plc_port)
# [解説 0660] この行の意図を確認するための注釈行です。
        self.var_dev_trig=tk.StringVar(value=self.cfg.dev_trig)
# [解説 0661] この行の意図を確認するための注釈行です。
        self.var_dev_ru=tk.StringVar(value=self.cfg.dev_ru)
# [解説 0662] この行の意図を確認するための注釈行です。
        self.var_dev_rd=tk.StringVar(value=self.cfg.dev_rd)
# [解説 0663] この行の意図を確認するための注釈行です。
        self.var_dev_done=tk.StringVar(value=self.cfg.dev_done)
# [解説 0664] この行の意図を確認するための注釈行です。
        self.var_dev_busy=tk.StringVar(value=self.cfg.dev_busy)
# [解説 0665] この行の意図を確認するための注釈行です。
        self.var_dev_err_to=tk.StringVar(value=self.cfg.dev_err_to)
# [解説 0666] この行の意図を確認するための注釈行です。
        self.var_dev_err_an=tk.StringVar(value=self.cfg.dev_err_an)
# [解説 0667] この行の意図を確認するための注釈行です。

# [解説 0668] この行の意図を確認するための注釈行です。
        # 生存カウンタ
# [解説 0669] この行の意図を確認するための注釈行です。
        self.hb_thread=None; self.hb_stop=False; self.hb_value=0
# [解説 0670] この行の意図を確認するための注釈行です。
        self.var_dev_alive=tk.StringVar(value=self.cfg.dev_alive)
# [解説 0671] この行の意図を確認するための注釈行です。
        self.var_alive_ms=tk.IntVar(value=self.cfg.alive_ms)
# [解説 0672] この行の意図を確認するための注釈行です。
        self.var_alive_step=tk.IntVar(value=self.cfg.alive_step)
# [解説 0673] この行の意図を確認するための注釈行です。
        self.var_alive_auto=tk.BooleanVar(value=self.cfg.alive_auto)
# [解説 0674] この行の意図を確認するための注釈行です。

# [解説 0675] この行の意図を確認するための注釈行です。
        # 一時ファイル管理
# [解説 0676] この行の意図を確認するための注釈行です。
        self.temp_max_files=tk.IntVar(value=self.cfg.temp_max_files)
# [解説 0677] この行の意図を確認するための注釈行です。

# [解説 0678] この行の意図を確認するための注釈行です。
        # CSV関連
# [解説 0679] この行の意図を確認するための注釈行です。
        self.csv_max_records=tk.IntVar(value=self.cfg.csv_max_records)
# [解説 0680] この行の意図を確認するための注釈行です。
        self.var_plc_shot_dir=tk.StringVar(value=self.cfg.plc_shot_dir)
# [解説 0681] この行の意図を確認するための注釈行です。

# [解説 0682] この行の意図を確認するための注釈行です。
        # 連続Grab状態
# [解説 0683] この行の意図を確認するための注釈行です。
        self.video_running=False
# [解説 0684] この行の意図を確認するための注釈行です。
        self.video_thread=None
# [解説 0685] この行の意図を確認するための注釈行です。
        self.video_stop=False
# [解説 0686] この行の意図を確認するための注釈行です。

# [解説 0687] この行の意図を確認するための注釈行です。
        # 手動操作ガード
# [解説 0688] この行の意図を確認するための注釈行です。
        self.manual_stopped=False
# [解説 0689] この行の意図を確認するための注釈行です。
        self.manual_disconnected=False
# [解説 0690] この行の意図を確認するための注釈行です。

# [解説 0691] この行の意図を確認するための注釈行です。
        # ログ（最新5行）
# [解説 0692] この行の意図を確認するための注釈行です。
        self._log_lines=deque(maxlen=5)
# [解説 0693] この行の意図を確認するための注釈行です。
        # 解析結果（最新5行）
# [解説 0694] この行の意図を確認するための注釈行です。
        self._result_lines=deque(maxlen=5)
# [解説 0695] この行の意図を確認するための注釈行です。

# [解説 0696] この行の意図を確認するための注釈行です。
        # UI
# [解説 0697] この行の意図を確認するための注釈行です。
        self._build_menu()
# [解説 0698] この行の意図を確認するための注釈行です。
        self._build_ui()
# [解説 0699] この行の意図を確認するための注釈行です。
        self._bind_traces()
# [解説 0700] この行の意図を確認するための注釈行です。
        self._auto_cleanup_temp_files()
# [解説 0701] この行の意図を確認するための注釈行です。
        self._post_status("起動完了。自動接続を試行します。")
# [解説 0702] この行の意図を確認するための注釈行です。

# [解説 0703] この行の意図を確認するための注釈行です。
        # 起動時の自動接続＆監視
# [解説 0704] この行の意図を確認するための注釈行です。
        self.after(300, self._auto_manager_start)
# [解説 0705] この行の意図を確認するための注釈行です。

# [解説 0706] この行の意図を確認するための注釈行です。
    # ---------- メニュー ----------
# [解説 0707] この行の意図を確認するための注釈行です。
    def _build_menu(self):
# [解説 0708] この行の意図を確認するための注釈行です。
        menubar=tk.Menu(self)
# [解説 0709] この行の意図を確認するための注釈行です。
        self.config(menu=menubar)
# [解説 0710] この行の意図を確認するための注釈行です。

# [解説 0711] この行の意図を確認するための注釈行です。
        m_settings=tk.Menu(menubar, tearoff=False)
# [解説 0712] この行の意図を確認するための注釈行です。
        menubar.add_cascade(label="設定", menu=m_settings)
# [解説 0713] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="PLC連携…", command=self._open_plc_settings)
# [解説 0714] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="カメラ設定…", command=self._open_camera_settings)
# [解説 0715] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="生存カウンタ…", command=self._open_hb_settings)
# [解説 0716] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="一時ファイル管理…", command=self._open_temp_settings)
# [解説 0717] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="結果CSV/保存先…", command=self._open_result_settings)
# [解説 0718] この行の意図を確認するための注釈行です。
        m_settings.add_separator()
# [解説 0719] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="出力フォルダを選択…", command=self.on_pick_outdir)
# [解説 0720] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="設定ファイルを開く", command=lambda: os.path.exists(CONFIG_PATH) and os.startfile(CONFIG_PATH))
# [解説 0721] この行の意図を確認するための注釈行です。
        m_settings.add_separator()
# [解説 0722] この行の意図を確認するための注釈行です。
        m_settings.add_command(label="終了", command=self.destroy)
# [解説 0723] この行の意図を確認するための注釈行です。

# [解説 0724] この行の意図を確認するための注釈行です。
        # 操作（完了テスト、RU/RDテストはここへ移動）
# [解説 0725] この行の意図を確認するための注釈行です。
        m_ops=tk.Menu(menubar, tearoff=False)
# [解説 0726] この行の意図を確認するための注釈行です。
        menubar.add_cascade(label="操作", menu=m_ops)
# [解説 0727] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="完了テスト（DONEパルス）", command=self.on_test_done)
# [解説 0728] この行の意図を確認するための注釈行です。
        m_ops.add_separator()
# [解説 0729] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="RU=1 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_ru.get().strip(), True)))
# [解説 0730] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="RU=0 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_ru.get().strip(), False)))
# [解説 0731] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="RD=1 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_rd.get().strip(), True)))
# [解説 0732] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="RD=0 書込", command=lambda: self._safe_plc(lambda: self.plc.write_bit(self.var_dev_rd.get().strip(), False)))
# [解説 0733] この行の意図を確認するための注釈行です。
        m_ops.add_separator()
# [解説 0734] この行の意図を確認するための注釈行です。
        m_ops.add_command(label="PLCエラークリア", command=self.on_clear_errors)
# [解説 0735] この行の意図を確認するための注釈行です。

# [解説 0736] この行の意図を確認するための注釈行です。
    # ---------- メインUI ----------
# [解説 0737] この行の意図を確認するための注釈行です。
    def _build_ui(self):
# [解説 0738] この行の意図を確認するための注釈行です。
        self.columnconfigure(1, weight=1)
# [解説 0739] この行の意図を確認するための注釈行です。
        self.rowconfigure(0, weight=1)
# [解説 0740] この行の意図を確認するための注釈行です。

# [解説 0741] この行の意図を確認するための注釈行です。
        # 左ペイン（スクロール可能） ※左にマージン
# [解説 0742] この行の意図を確認するための注釈行です。
        left_wrap=ScrollFrame(self)
# [解説 0743] この行の意図を確認するための注釈行です。
        left_wrap.grid(row=0, column=0, sticky="nsw", padx=(12,0))
# [解説 0744] この行の意図を確認するための注釈行です。
        left=left_wrap.inner
# [解説 0745] この行の意図を確認するための注釈行です。
        left.grid_columnconfigure(0, weight=1, minsize=380)  # 幅不足対策：最低幅
# [解説 0746] この行の意図を確認するための注釈行です。

# [解説 0747] この行の意図を確認するための注釈行です。
        # 1) 画像入力
# [解説 0748] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="1) 画像ファイル / 撮像").grid(row=0, column=0, sticky="w", pady=(4,2))
# [解説 0749] この行の意図を確認するための注釈行です。
        # --- 「画像を選ぶ」を単独行に分離 ---
# [解説 0750] この行の意図を確認するための注釈行です。
        row_pick=ttk.Frame(left); row_pick.grid(row=1, column=0, sticky="we")
# [解説 0751] この行の意図を確認するための注釈行です。
        ttk.Button(row_pick, text="画像を選ぶ（複数可）", command=self.on_pick_files, bootstyle=PRIMARY).pack(side="left")
# [解説 0752] この行の意図を確認するための注釈行です。

# [解説 0753] この行の意図を確認するための注釈行です。
        # その下の行に 撮像 / 連続Grab開始 / 連続Grab停止
# [解説 0754] この行の意図を確認するための注釈行です。
        row_cam=ttk.Frame(left); row_cam.grid(row=2, column=0, sticky="we", pady=(4,0))
# [解説 0755] この行の意図を確認するための注釈行です。
        ttk.Button(row_cam, text="撮像（Basler）", command=self.on_capture_basler, bootstyle=SUCCESS).pack(side="left")
# [解説 0756] この行の意図を確認するための注釈行です。
        ttk.Button(row_cam, text="連続Grab開始", command=self.on_video_start).pack(side="left", padx=6)
# [解説 0757] この行の意図を確認するための注釈行です。
        ttk.Button(row_cam, text="連続Grab停止", command=self.on_video_stop).pack(side="left")
# [解説 0758] この行の意図を確認するための注釈行です。

# [解説 0759] この行の意図を確認するための注釈行です。
        self.lb_files = tk.Listbox(left, height=10, selectmode=tk.EXTENDED)
# [解説 0760] この行の意図を確認するための注釈行です。
        self.lb_files.grid(row=3, column=0, sticky="we")
# [解説 0761] この行の意図を確認するための注釈行です。
        self.lb_files.bind("<<ListboxSelect>>", self._on_listbox_select)
# [解説 0762] この行の意図を確認するための注釈行です。
        sb=ttk.Scrollbar(left, orient="vertical", command=self.lb_files.yview)
# [解説 0763] この行の意図を確認するための注釈行です。
        self.lb_files.configure(yscrollcommand=sb.set); sb.grid(row=3, column=1, sticky="ns")
# [解説 0764] この行の意図を確認するための注釈行です。

# [解説 0765] この行の意図を確認するための注釈行です。
        # 2) 出力先
# [解説 0766] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="2) 出力フォルダ（CSV & 画像）").grid(row=4, column=0, sticky="w", pady=(8,2))
# [解説 0767] この行の意図を確認するための注釈行です。
        ttk.Label(left, text=(self.output_dir if self.output_dir else "未指定（元画像と同じ場所）"), bootstyle=INFO).grid(row=5, column=0, sticky="w")
# [解説 0768] この行の意図を確認するための注釈行です。

# [解説 0769] この行の意図を確認するための注釈行です。
        # 3) 基本パラメータ
# [解説 0770] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="3) 基本パラメータ").grid(row=6, column=0, sticky="w", pady=(12,2))
# [解説 0771] この行の意図を確認するための注釈行です。
        frm_params=ttk.Frame(left); frm_params.grid(row=7, column=0, sticky="we")
# [解説 0772] この行の意図を確認するための注釈行です。
        ttk.Label(frm_params, text="trim_ratio_x:").grid(row=0, column=0, sticky="e")
# [解説 0773] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_params, from_=0.0, to=0.95, increment=0.01, textvariable=self.trim_ratio_x, width=6).grid(row=0, column=1, padx=4, pady=2)
# [解説 0774] この行の意図を確認するための注釈行です。
        ttk.Label(frm_params, text="trim_ratio_y:").grid(row=1, column=0, sticky="e")
# [解説 0775] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_params, from_=0.0, to=0.95, increment=0.01, textvariable=self.trim_ratio_y, width=6).grid(row=1, column=1, padx=4, pady=2)
# [解説 0776] この行の意図を確認するための注釈行です。
        ttk.Label(frm_params, text="diff_thresh:").grid(row=2, column=0, sticky="e")
# [解説 0777] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_params, from_=1, to=1000000, increment=50, textvariable=self.diff_thresh, width=10).grid(row=2, column=1, padx=4, pady=2)
# [解説 0778] この行の意図を確認するための注釈行です。

# [解説 0779] この行の意図を確認するための注釈行です。
        ttk.Checkbutton(frm_params, text="画像を左右反転してから解析", variable=self.flip_horizontal).grid(row=3, column=0, columnspan=2, sticky="w")
# [解説 0780] この行の意図を確認するための注釈行です。

# [解説 0781] この行の意図を確認するための注釈行です。
        # 4) 直線近似パラメータ
# [解説 0782] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="4) 直線近似パラメータ").grid(row=8, column=0, sticky="w", pady=(12,2))
# [解説 0783] この行の意図を確認するための注釈行です。
        frm_line=ttk.Frame(left); frm_line.grid(row=9, column=0, sticky="we")
# [解説 0784] この行の意図を確認するための注釈行です。
        ttk.Label(frm_line, text="band_top:").grid(row=0, column=0, sticky="e")
# [解説 0785] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_top, width=6).grid(row=0, column=1, padx=4, pady=2)
# [解説 0786] この行の意図を確認するための注釈行です。
        ttk.Label(frm_line, text="band_right:").grid(row=1, column=0, sticky="e")
# [解説 0787] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_right, width=6).grid(row=1, column=1, padx=4, pady=2)
# [解説 0788] この行の意図を確認するための注釈行です。
        ttk.Label(frm_line, text="band_bottom:").grid(row=2, column=0, sticky="e")
# [解説 0789] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_line, from_=5, to=300, increment=1, textvariable=self.band_bottom, width=6).grid(row=2, column=1, padx=4, pady=2)
# [解説 0790] この行の意図を確認するための注釈行です。
        ttk.Label(frm_line, text="corner_exclude_x_px:").grid(row=3, column=0, sticky="e")
# [解説 0791] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_line, from_=0, to=500, increment=5, textvariable=self.corner_exclude_x_px, width=6).grid(row=3, column=1, padx=4, pady=2)
# [解説 0792] この行の意図を確認するための注釈行です。
        ttk.Label(frm_line, text="corner_exclude_y_px:").grid(row=4, column=0, sticky="e")
# [解説 0793] この行の意図を確認するための注釈行です。
        ttk.Spinbox(frm_line, from_=0, to=200, increment=5, textvariable=self.corner_exclude_y_px, width=6).grid(row=4, column=1, padx=4, pady=2)
# [解説 0794] この行の意図を確認するための注釈行です。

# [解説 0795] この行の意図を確認するための注釈行です。
        ttk.Checkbutton(left, text="パラメータ変更で自動プレビュー", variable=self.auto_preview).grid(row=10, column=0, sticky="w", pady=(8,0))
# [解説 0796] この行の意図を確認するための注釈行です。

# [解説 0797] この行の意図を確認するための注釈行です。
        # 5) 画像処理 実行
# [解説 0798] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="5) 画像処理 実行").grid(row=11, column=0, sticky="w", pady=(8,2))
# [解説 0799] この行の意図を確認するための注釈行です。
        frm_btns=ttk.Frame(left); frm_btns.grid(row=12, column=0, sticky="we")
# [解説 0800] この行の意図を確認するための注釈行です。
        ttk.Button(frm_btns, text="選択中をプレビュー", command=self.on_preview, bootstyle=PRIMARY).grid(row=0, column=0, padx=2, pady=2)
# [解説 0801] この行の意図を確認するための注釈行です。
        ttk.Button(frm_btns, text="すべて処理＆保存", command=self.on_batch_process, bootstyle=SUCCESS).grid(row=0, column=1, padx=2, pady=2)
# [解説 0802] この行の意図を確認するための注釈行です。

# [解説 0803] この行の意図を確認するための注釈行です。
        # 6) PLC 操作（※パラメータ入力は撤去、ボタンのみ残す）
# [解説 0804] この行の意図を確認するための注釈行です。
        ttk.Label(left, text="6) PLC 監視・操作").grid(row=13, column=0, sticky="w", pady=(14,4))
# [解説 0805] この行の意図を確認するための注釈行です。
        plc=ttk.Labelframe(left, text="PLC Trigger / I/O", padding=8)
# [解説 0806] この行の意図を確認するための注釈行です。
        plc.grid(row=14, column=0, sticky="we")
# [解説 0807] この行の意図を確認するための注釈行です。

# [解説 0808] この行の意図を確認するための注釈行です。
        r_conn=ttk.Frame(plc); r_conn.pack(fill="x", pady=2)
# [解説 0809] この行の意図を確認するための注釈行です。
        ttk.Button(r_conn, text="接続", command=self.on_plc_connect, bootstyle=SUCCESS).pack(side="left")
# [解説 0810] この行の意図を確認するための注釈行です。
        ttk.Button(r_conn, text="切断", command=self.on_plc_disconnect).pack(side="left", padx=6)
# [解説 0811] この行の意図を確認するための注釈行です。
        self.lbl_plc_target=ttk.Label(r_conn, text=f"ターゲット: {self.var_plc_ip.get()}:{self.var_plc_port.get()}", bootstyle=INFO)
# [解説 0812] この行の意図を確認するための注釈行です。
        self.lbl_plc_target.pack(side="left", padx=8)
# [解説 0813] この行の意図を確認するための注釈行です。

# [解説 0814] この行の意図を確認するための注釈行です。
        r_ctrl=ttk.Frame(plc); r_ctrl.pack(fill="x", pady=6)
# [解説 0815] この行の意図を確認するための注釈行です。
        ttk.Button(r_ctrl, text="監視開始", command=self.on_plc_watch_start, bootstyle=PRIMARY).pack(side="left")
# [解説 0816] この行の意図を確認するための注釈行です。
        ttk.Button(r_ctrl, text="停止", command=lambda: self.on_plc_watch_stop(manual=True)).pack(side="left", padx=6)
# [解説 0817] この行の意図を確認するための注釈行です。

# [解説 0818] この行の意図を確認するための注釈行です。
        # 右側（プレビュー）
# [解説 0819] この行の意図を確認するための注釈行です。
        right=ttk.Frame(self, padding=8); right.grid(row=0, column=1, sticky="nsew")
# [解説 0820] この行の意図を確認するための注釈行です。
        right.rowconfigure(2, weight=1); right.columnconfigure(0, weight=1)
# [解説 0821] この行の意図を確認するための注釈行です。
        topbar=ttk.Frame(right); topbar.grid(row=0, column=0, sticky="we")
# [解説 0822] この行の意図を確認するための注釈行です。
        ttk.Label(topbar, text="結果プレビュー").pack(side="left")
# [解説 0823] この行の意図を確認するための注釈行です。
        self.zoom_label=ttk.Label(topbar, text="100%"); self.zoom_label.pack(side="right", padx=4)
# [解説 0824] この行の意図を確認するための注釈行です。
        ttk.Button(topbar, text="100%", command=self.on_zoom_100).pack(side="right")
# [解説 0825] この行の意図を確認するための注釈行です。
        ttk.Button(topbar, text="フィット", command=self.on_fit).pack(side="right", padx=(0,6))
# [解説 0826] この行の意図を確認するための注釈行です。
        ttk.Button(topbar, text="－", width=3, command=self.on_zoom_out).pack(side="right")
# [解説 0827] この行の意図を確認するための注釈行です。
        ttk.Button(topbar, text="＋", width=3, command=self.on_zoom_in).pack(side="right")
# [解説 0828] この行の意図を確認するための注釈行です。

# [解説 0829] この行の意図を確認するための注釈行です。
        self.preview_area=ttk.Frame(right, relief="groove")
# [解説 0830] この行の意図を確認するための注釈行です。
        self.preview_area.grid(row=2, column=0, sticky="nsew", pady=(6,0))
# [解説 0831] この行の意図を確認するための注釈行です。
        self.preview_area.rowconfigure(0, weight=1); self.preview_area.columnconfigure(0, weight=1)
# [解説 0832] この行の意図を確認するための注釈行です。
        self.canvas=ZoomPanCanvas(self.preview_area, bg="#222"); self.canvas.grid(row=0, column=0, sticky="nsew")
# [解説 0833] この行の意図を確認するための注釈行です。

# [解説 0834] この行の意図を確認するための注釈行です。
        # ステータス & 解析結果（並列）
# [解説 0835] この行の意図を確認するための注釈行です。
        info_row=ttk.Frame(right); info_row.grid(row=3, column=0, sticky="we", pady=(6,0))
# [解説 0836] この行の意図を確認するための注釈行です。
        info_row.columnconfigure(0, weight=1)
# [解説 0837] この行の意図を確認するための注釈行です。
        info_row.columnconfigure(1, weight=3)
# [解説 0838] この行の意図を確認するための注釈行です。

# [解説 0839] この行の意図を確認するための注釈行です。
        logframe=ttk.Frame(info_row)
# [解説 0840] この行の意図を確認するための注釈行です。
        logframe.grid(row=0, column=0, sticky="nsew", padx=(0,6))
# [解説 0841] この行の意図を確認するための注釈行です。
        ttk.Label(logframe, text="ステータス（最新5件）", bootstyle=INFO).pack(anchor="w")
# [解説 0842] この行の意図を確認するための注釈行です。
        self.txt_log=tk.Text(logframe, height=5, width=36, state="disabled", wrap="none")
# [解説 0843] この行の意図を確認するための注釈行です。
        self.txt_log.pack(fill="both", expand=True)
# [解説 0844] この行の意図を確認するための注釈行です。

# [解説 0845] この行の意図を確認するための注釈行です。
        resultframe=ttk.Frame(info_row)
# [解説 0846] この行の意図を確認するための注釈行です。
        resultframe.grid(row=0, column=1, sticky="nsew")
# [解説 0847] この行の意図を確認するための注釈行です。
        ttk.Label(resultframe, text="解析結果", bootstyle=INFO).pack(anchor="w")
# [解説 0848] この行の意図を確認するための注釈行です。
        self.txt_result=tk.Text(resultframe, height=5, state="disabled", wrap="word")
# [解説 0849] この行の意図を確認するための注釈行です。
        self.txt_result.pack(fill="both", expand=True)
# [解説 0850] この行の意図を確認するための注釈行です。

# [解説 0851] この行の意図を確認するための注釈行です。
        self.canvas.bind("<Configure>", lambda _e: self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%"))
# [解説 0852] この行の意図を確認するための注釈行です。

# [解説 0853] この行の意図を確認するための注釈行です。
    # ---------- 設定ダイアログ ----------
# [解説 0854] この行の意図を確認するための注釈行です。
    def _open_plc_settings(self):
# [解説 0855] この行の意図を確認するための注釈行です。
        win=tk.Toplevel(self); win.title("PLC連携 設定"); win.transient(self); win.grab_set()
# [解説 0856] この行の意図を確認するための注釈行です。
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
# [解説 0857] この行の意図を確認するための注釈行です。
        # IP/Port
# [解説 0858] この行の意図を確認するための注釈行です。
        sec1=ttk.Labelframe(frm, text="接続先", padding=8); sec1.pack(fill="x", pady=6)
# [解説 0859] この行の意図を確認するための注釈行です。
        r=ttk.Frame(sec1); r.pack(fill="x")
# [解説 0860] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="PLC IP").pack(side="left"); ttk.Entry(r, textvariable=self.var_plc_ip, width=16).pack(side="left", padx=6)
# [解説 0861] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="Port").pack(side="left"); ttk.Entry(r, textvariable=self.var_plc_port, width=8).pack(side="left", padx=6)
# [解説 0862] この行の意図を確認するための注釈行です。

# [解説 0863] この行の意図を確認するための注釈行です。
        # デバイス
# [解説 0864] この行の意図を確認するための注釈行です。
        sec2=ttk.Labelframe(frm, text="デバイス割当", padding=8); sec2.pack(fill="x", pady=6)
# [解説 0865] この行の意図を確認するための注釈行です。
        grid=ttk.Frame(sec2); grid.pack(fill="x")
# [解説 0866] この行の意図を確認するための注釈行です。
        def row(label, var):
# [解説 0867] この行の意図を確認するための注釈行です。
            rr=ttk.Frame(grid); rr.pack(fill="x", pady=2)
# [解説 0868] この行の意図を確認するための注釈行です。
            ttk.Label(rr, text=label, width=16).pack(side="left")
# [解説 0869] この行の意図を確認するための注釈行です。
            ttk.Entry(rr, textvariable=var, width=12).pack(side="left")
# [解説 0870] この行の意図を確認するための注釈行です。
        row("トリガ(読)", self.var_dev_trig)
# [解説 0871] この行の意図を確認するための注釈行です。
        row("結果RU(書)", self.var_dev_ru)
# [解説 0872] この行の意図を確認するための注釈行です。
        row("結果RD(書)", self.var_dev_rd)
# [解説 0873] この行の意図を確認するための注釈行です。
        row("完了(パルス)", self.var_dev_done)
# [解説 0874] この行の意図を確認するための注釈行です。
        row("ビジー(書)", self.var_dev_busy)
# [解説 0875] この行の意図を確認するための注釈行です。
        row("Err Timeout", self.var_dev_err_to)
# [解説 0876] この行の意図を確認するための注釈行です。
        row("Err 解析失敗", self.var_dev_err_an)
# [解説 0877] この行の意図を確認するための注釈行です。

# [解説 0878] この行の意図を確認するための注釈行です。
        # 撮像条件
# [解説 0879] この行の意図を確認するための注釈行です。
        sec3=ttk.Labelframe(frm, text="撮像条件", padding=8); sec3.pack(fill="x", pady=6)
# [解説 0880] この行の意図を確認するための注釈行です。
        r3=ttk.Frame(sec3); r3.pack(fill="x")
# [解説 0881] この行の意図を確認するための注釈行です。
        ttk.Checkbutton(r3, text="ソフトウェアトリガで撮像", variable=self.var_use_sw_trig).pack(side="left")
# [解説 0882] この行の意図を確認するための注釈行です。
        ttk.Label(r3, text="撮像Timeout[ms]").pack(side="left", padx=(12,2))
# [解説 0883] この行の意図を確認するための注釈行です。
        ttk.Entry(r3, textvariable=self.var_timeout_ms, width=8).pack(side="left", padx=(0,8))
# [解説 0884] この行の意図を確認するための注釈行です。
        ttk.Label(r3, text="完了パルス幅[ms]").pack(side="left", padx=(12,2))
# [解説 0885] この行の意図を確認するための注釈行です。
        ttk.Entry(r3, textvariable=self.var_done_ms, width=8).pack(side="left")
# [解説 0886] この行の意図を確認するための注釈行です。

# [解説 0887] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="変更は即保存されます。閉じるときは右上×で閉じてください。", bootstyle=INFO).pack(anchor="w", pady=(8,0))
# [解説 0888] この行の意図を確認するための注釈行です。

# [解説 0889] この行の意図を確認するための注釈行です。
        # IP/Port 表示の同期
# [解説 0890] この行の意図を確認するための注釈行です。
        def sync_target(*_):
# [解説 0891] この行の意図を確認するための注釈行です。
            self.lbl_plc_target.configure(text=f"ターゲット: {self.var_plc_ip.get()}:{self.var_plc_port.get()}")
# [解説 0892] この行の意図を確認するための注釈行です。
        self.var_plc_ip.trace_add("write", sync_target)
# [解説 0893] この行の意図を確認するための注釈行です。
        self.var_plc_port.trace_add("write", sync_target)
# [解説 0894] この行の意図を確認するための注釈行です。

# [解説 0895] この行の意図を確認するための注釈行です。
    def _open_camera_settings(self):
# [解説 0896] この行の意図を確認するための注釈行です。
        win=tk.Toplevel(self); win.title("カメラ設定"); win.transient(self); win.grab_set()
# [解説 0897] この行の意図を確認するための注釈行です。
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
# [解説 0898] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="接続するGigEカメラを選択してください。", bootstyle=INFO).pack(anchor="w")
# [解説 0899] この行の意図を確認するための注釈行です。
        devices=list_basler_devices()
# [解説 0900] この行の意図を確認するための注釈行です。
        if not devices:
# [解説 0901] この行の意図を確認するための注釈行です。
            ttk.Label(frm, text="カメラが検出できません。pypylonの導入や接続を確認してください。", bootstyle=WARNING).pack(anchor="w", pady=(8,0))
# [解説 0902] この行の意図を確認するための注釈行です。
            return
# [解説 0903] この行の意図を確認するための注釈行です。
        labels=[label for _idx, label in devices]
# [解説 0904] この行の意図を確認するための注釈行です。
        idx_map={label: idx for idx, label in devices}
# [解説 0905] この行の意図を確認するための注釈行です。
        cmb=ttk.Combobox(frm, state="readonly", values=labels)
# [解説 0906] この行の意図を確認するための注釈行です。
        current_label=next((label for idx, label in devices if idx==self.var_camera_index.get()), labels[0])
# [解説 0907] この行の意図を確認するための注釈行です。
        cmb.set(current_label)
# [解説 0908] この行の意図を確認するための注釈行です。
        cmb.pack(anchor="w", pady=(8,0))
# [解説 0909] この行の意図を確認するための注釈行です。
        def on_select(_event=None):
# [解説 0910] この行の意図を確認するための注釈行です。
            label=cmb.get()
# [解説 0911] この行の意図を確認するための注釈行です。
            self.var_camera_index.set(idx_map.get(label, 0))
# [解説 0912] この行の意図を確認するための注釈行です。
        cmb.bind("<<ComboboxSelected>>", on_select)
# [解説 0913] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w", pady=(8,0))
# [解説 0914] この行の意図を確認するための注釈行です。

# [解説 0915] この行の意図を確認するための注釈行です。
    def _open_hb_settings(self):
# [解説 0916] この行の意図を確認するための注釈行です。
        win=tk.Toplevel(self); win.title("生存カウンタ 設定"); win.transient(self); win.grab_set()
# [解説 0917] この行の意図を確認するための注釈行です。
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
# [解説 0918] この行の意図を確認するための注釈行です。
        r=ttk.Frame(frm); r.pack(fill="x", pady=2)
# [解説 0919] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="Dデバイス").pack(side="left"); ttk.Entry(r, textvariable=self.var_dev_alive, width=10).pack(side="left", padx=6)
# [解説 0920] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="周期[ms]").pack(side="left", padx=(12,2)); ttk.Entry(r, textvariable=self.var_alive_ms, width=8).pack(side="left")
# [解説 0921] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="増分").pack(side="left", padx=(12,2)); ttk.Entry(r, textvariable=self.var_alive_step, width=6).pack(side="left")
# [解説 0922] この行の意図を確認するための注釈行です。
        ttk.Checkbutton(frm, text="PLC接続時に自動開始", variable=self.var_alive_auto).pack(anchor="w", pady=(8,2))
# [解説 0923] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w")
# [解説 0924] この行の意図を確認するための注釈行です。

# [解説 0925] この行の意図を確認するための注釈行です。
    def _open_temp_settings(self):
# [解説 0926] この行の意図を確認するための注釈行です。
        win=tk.Toplevel(self); win.title("一時ファイル管理"); win.transient(self); win.grab_set()
# [解説 0927] この行の意図を確認するための注釈行です。
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
# [解説 0928] この行の意図を確認するための注釈行です。
        r=ttk.Frame(frm); r.pack(fill="x", pady=2)
# [解説 0929] この行の意図を確認するための注釈行です。
        ttk.Label(r, text="保持上限(枚)").pack(side="left"); ttk.Entry(r, textvariable=self.temp_max_files, width=8).pack(side="left", padx=6)
# [解説 0930] この行の意図を確認するための注釈行です。
        ttk.Button(frm, text="今すぐ清掃", command=self._auto_cleanup_temp_files).pack(anchor="w", pady=(8,2))
# [解説 0931] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="BaslerShot_*/PLCshot_* を古い順に削除します。", bootstyle=INFO).pack(anchor="w")
# [解説 0932] この行の意図を確認するための注釈行です。

# [解説 0933] この行の意図を確認するための注釈行です。
    def _open_result_settings(self):
# [解説 0934] この行の意図を確認するための注釈行です。
        win=tk.Toplevel(self); win.title("結果CSV/保存先 設定"); win.transient(self); win.grab_set()
# [解説 0935] この行の意図を確認するための注釈行です。
        frm=ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
# [解説 0936] この行の意図を確認するための注釈行です。
        r1=ttk.Frame(frm); r1.pack(fill="x", pady=2)
# [解説 0937] この行の意図を確認するための注釈行です。
        ttk.Label(r1, text="結果CSV 最大レコード数").pack(side="left")
# [解説 0938] この行の意図を確認するための注釈行です。
        ttk.Entry(r1, textvariable=self.csv_max_records, width=8).pack(side="left", padx=6)
# [解説 0939] この行の意図を確認するための注釈行です。
        r2=ttk.Frame(frm); r2.pack(fill="x", pady=8)
# [解説 0940] この行の意図を確認するための注釈行です。
        ttk.Label(r2, text="PLC撮像 画像保存先（空=Temp）").pack(side="left")
# [解説 0941] この行の意図を確認するための注釈行です。
        ttk.Entry(r2, textvariable=self.var_plc_shot_dir, width=40).pack(side="left", padx=6)
# [解説 0942] この行の意図を確認するための注釈行です。
        ttk.Button(r2, text="参照…", command=self._pick_plcshot_dir).pack(side="left")
# [解説 0943] この行の意図を確認するための注釈行です。
        ttk.Label(frm, text="変更は即保存されます。", bootstyle=INFO).pack(anchor="w", pady=(8,0))
# [解説 0944] この行の意図を確認するための注釈行です。

# [解説 0945] この行の意図を確認するための注釈行です。
    def _pick_plcshot_dir(self):
# [解説 0946] この行の意図を確認するための注釈行です。
        d=filedialog.askdirectory(title="PLCトリガで保存する画像の保存先フォルダを選択")
# [解説 0947] この行の意図を確認するための注釈行です。
        if d:
# [解説 0948] この行の意図を確認するための注釈行です。
            self.var_plc_shot_dir.set(d)
# [解説 0949] この行の意図を確認するための注釈行です。

# [解説 0950] この行の意図を確認するための注釈行です。
    # ---------- 設定トレース（即保存 + 自動プレビュー） ----------
# [解説 0951] この行の意図を確認するための注釈行です。
    def _bind_traces(self):
# [解説 0952] この行の意図を確認するための注釈行です。
        """Tk変数の変更を捕捉して保存。解析パラメータは自動プレビューもスケジュール"""
# [解説 0953] この行の意図を確認するための注釈行です。
        def save_cfg(*_):
# [解説 0954] この行の意図を確認するための注釈行です。
            if self._trace_lock:
# [解説 0955] この行の意図を確認するための注釈行です。
                return
# [解説 0956] この行の意図を確認するための注釈行です。
            self._sync_cfg_from_vars()
# [解説 0957] この行の意図を確認するための注釈行です。
            self.cfg.save()
# [解説 0958] この行の意図を確認するための注釈行です。

# [解説 0959] この行の意図を確認するための注釈行です。
        # 自動プレビュー対象（解析に影響）
# [解説 0960] この行の意図を確認するための注釈行です。
        preview_vars = (
# [解説 0961] この行の意図を確認するための注釈行です。
            self.trim_ratio_x, self.trim_ratio_y, self.diff_thresh,
# [解説 0962] この行の意図を確認するための注釈行です。
            self.band_top, self.band_right, self.band_bottom,
# [解説 0963] この行の意図を確認するための注釈行です。
            self.corner_exclude_x_px, self.corner_exclude_y_px,
# [解説 0964] この行の意図を確認するための注釈行です。
            self.flip_horizontal,
# [解説 0965] この行の意図を確認するための注釈行です。
            self.auto_preview,  # ONにした瞬間にもプレビューしたい
# [解説 0966] この行の意図を確認するための注釈行です。
        )
# [解説 0967] この行の意図を確認するための注釈行です。
        # 保存のみ対象（PLC/HB/保存先 他）
# [解説 0968] この行の意図を確認するための注釈行です。
        non_preview_vars = (
# [解説 0969] この行の意図を確認するための注釈行です。
            self.var_plc_ip, self.var_plc_port, self.var_dev_trig, self.var_dev_ru, self.var_dev_rd,
# [解説 0970] この行の意図を確認するための注釈行です。
            self.var_dev_done, self.var_dev_busy, self.var_dev_err_to, self.var_dev_err_an,
# [解説 0971] この行の意図を確認するための注釈行です。
            self.var_use_sw_trig, self.var_timeout_ms, self.var_done_ms,
# [解説 0972] この行の意図を確認するための注釈行です。
            self.var_dev_alive, self.var_alive_ms, self.var_alive_step, self.var_alive_auto,
# [解説 0973] この行の意図を確認するための注釈行です。
            self.temp_max_files, self.csv_max_records, self.var_plc_shot_dir,
# [解説 0974] この行の意図を確認するための注釈行です。
            self.var_camera_index
# [解説 0975] この行の意図を確認するための注釈行です。
        )
# [解説 0976] この行の意図を確認するための注釈行です。

# [解説 0977] この行の意図を確認するための注釈行です。
        def bind_with_preview(v):
# [解説 0978] この行の意図を確認するための注釈行です。
            v.trace_add("write", lambda *args: (save_cfg(), self._schedule_auto_preview()))
# [解説 0979] この行の意図を確認するための注釈行です。
        def bind_save_only(v):
# [解説 0980] この行の意図を確認するための注釈行です。
            v.trace_add("write", lambda *args: save_cfg())
# [解説 0981] この行の意図を確認するための注釈行です。

# [解説 0982] この行の意図を確認するための注釈行です。
        for v in preview_vars: bind_with_preview(v)
# [解説 0983] この行の意図を確認するための注釈行です。
        for v in non_preview_vars: bind_save_only(v)
# [解説 0984] この行の意図を確認するための注釈行です。

# [解説 0985] この行の意図を確認するための注釈行です。
    def _schedule_auto_preview(self):
# [解説 0986] この行の意図を確認するための注釈行です。
        """パラメータ変更時の自動プレビュー（200msデバウンス）"""
# [解説 0987] この行の意図を確認するための注釈行です。
        try:
# [解説 0988] この行の意図を確認するための注釈行です。
            if not bool(self.auto_preview.get()):
# [解説 0989] この行の意図を確認するための注釈行です。
                return
# [解説 0990] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 0991] この行の意図を確認するための注釈行です。
            return
# [解説 0992] この行の意図を確認するための注釈行です。
        if not self.file_paths:
# [解説 0993] この行の意図を確認するための注釈行です。
            return
# [解説 0994] この行の意図を確認するための注釈行です。
        if self.last_sel_index is None and not self.lb_files.curselection():
# [解説 0995] この行の意図を確認するための注釈行です。
            return
# [解説 0996] この行の意図を確認するための注釈行です。
        if getattr(self, "video_running", False):
# [解説 0997] この行の意図を確認するための注釈行です。
            return
# [解説 0998] この行の意図を確認するための注釈行です。
        if self._preview_job:
# [解説 0999] この行の意図を確認するための注釈行です。
            try:
# [解説 1000] この行の意図を確認するための注釈行です。
                self.after_cancel(self._preview_job)
# [解説 1001] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 1002] この行の意図を確認するための注釈行です。
                pass
# [解説 1003] この行の意図を確認するための注釈行です。
        self._preview_job = self.after(200, self.on_preview)
# [解説 1004] この行の意図を確認するための注釈行です。

# [解説 1005] この行の意図を確認するための注釈行です。
    def _sync_cfg_from_vars(self):
# [解説 1006] この行の意図を確認するための注釈行です。
        self.cfg.trim_ratio_x=self.trim_ratio_x.get()
# [解説 1007] この行の意図を確認するための注釈行です。
        self.cfg.trim_ratio_y=self.trim_ratio_y.get()
# [解説 1008] この行の意図を確認するための注釈行です。
        self.cfg.diff_thresh=self.diff_thresh.get()
# [解説 1009] この行の意図を確認するための注釈行です。
        self.cfg.band_top=self.band_top.get()
# [解説 1010] この行の意図を確認するための注釈行です。
        self.cfg.band_right=self.band_right.get()
# [解説 1011] この行の意図を確認するための注釈行です。
        self.cfg.band_bottom=self.band_bottom.get()
# [解説 1012] この行の意図を確認するための注釈行です。
        self.cfg.corner_exclude_x_px=self.corner_exclude_x_px.get()
# [解説 1013] この行の意図を確認するための注釈行です。
        self.cfg.corner_exclude_y_px=self.corner_exclude_y_px.get()
# [解説 1014] この行の意図を確認するための注釈行です。
        self.cfg.auto_preview=bool(self.auto_preview.get())
# [解説 1015] この行の意図を確認するための注釈行です。
        self.cfg.flip_horizontal=bool(self.flip_horizontal.get())
# [解説 1016] この行の意図を確認するための注釈行です。
        self.cfg.camera_index=int(self.var_camera_index.get())
# [解説 1017] この行の意図を確認するための注釈行です。
        self.cfg.output_dir=self.output_dir or ""
# [解説 1018] この行の意図を確認するための注釈行です。
        self.cfg.plc_ip=self.var_plc_ip.get().strip()
# [解説 1019] この行の意図を確認するための注釈行です。
        self.cfg.plc_port=int(self.var_plc_port.get())
# [解説 1020] この行の意図を確認するための注釈行です。
        self.cfg.dev_trig=self.var_dev_trig.get().strip()
# [解説 1021] この行の意図を確認するための注釈行です。
        self.cfg.dev_ru=self.var_dev_ru.get().strip()
# [解説 1022] この行の意図を確認するための注釈行です。
        self.cfg.dev_rd=self.var_dev_rd.get().strip()
# [解説 1023] この行の意図を確認するための注釈行です。
        self.cfg.dev_done=self.var_dev_done.get().strip()
# [解説 1024] この行の意図を確認するための注釈行です。
        self.cfg.dev_busy=self.var_dev_busy.get().strip()
# [解説 1025] この行の意図を確認するための注釈行です。
        self.cfg.dev_err_to=self.var_dev_err_to.get().strip()
# [解説 1026] この行の意図を確認するための注釈行です。
        self.cfg.dev_err_an=self.var_dev_err_an.get().strip()
# [解説 1027] この行の意図を確認するための注釈行です。
        self.cfg.use_sw_trig=bool(self.var_use_sw_trig.get())
# [解説 1028] この行の意図を確認するための注釈行です。
        self.cfg.timeout_ms=int(self.var_timeout_ms.get())
# [解説 1029] この行の意図を確認するための注釈行です。
        self.cfg.done_ms=int(self.var_done_ms.get())
# [解説 1030] この行の意図を確認するための注釈行です。
        self.cfg.dev_alive=self.var_dev_alive.get().strip()
# [解説 1031] この行の意図を確認するための注釈行です。
        self.cfg.alive_ms=int(self.var_alive_ms.get())
# [解説 1032] この行の意図を確認するための注釈行です。
        self.cfg.alive_step=int(self.var_alive_step.get())
# [解説 1033] この行の意図を確認するための注釈行です。
        self.cfg.alive_auto=bool(self.var_alive_auto.get())
# [解説 1034] この行の意図を確認するための注釈行です。
        self.cfg.temp_max_files=int(self.temp_max_files.get())
# [解説 1035] この行の意図を確認するための注釈行です。
        self.cfg.csv_max_records=int(self.csv_max_records.get())
# [解説 1036] この行の意図を確認するための注釈行です。
        self.cfg.plc_shot_dir=self.var_plc_shot_dir.get().strip()
# [解説 1037] この行の意図を確認するための注釈行です。

# [解説 1038] この行の意図を確認するための注釈行です。
    # ---------- 左ペイン操作 ----------
# [解説 1039] この行の意図を確認するための注釈行です。
    def _on_listbox_select(self,_evt=None):
# [解説 1040] この行の意図を確認するための注釈行です。
        sel=self.lb_files.curselection()
# [解説 1041] この行の意図を確認するための注釈行です。
        if sel:
# [解説 1042] この行の意図を確認するための注釈行です。
            self.last_sel_index=sel[0]
# [解説 1043] この行の意図を確認するための注釈行です。
            if self.auto_preview.get(): self.on_preview()
# [解説 1044] この行の意図を確認するための注釈行です。

# [解説 1045] この行の意図を確認するための注釈行です。
    def on_pick_files(self):
# [解説 1046] この行の意図を確認するための注釈行です。
        paths=filedialog.askopenfilenames(
# [解説 1047] この行の意図を確認するための注釈行です。
            title="画像を選択してください（複数選択可）",
# [解説 1048] この行の意図を確認するための注釈行です。
            filetypes=[("画像ファイル","*.bmp;*.jpg;*.jpeg;*.png"),("すべてのファイル","*.*")]
# [解説 1049] この行の意図を確認するための注釈行です。
        )
# [解説 1050] この行の意図を確認するための注釈行です。
        if not paths: return
# [解説 1051] この行の意図を確認するための注釈行です。
        self.file_paths=list(paths)
# [解説 1052] この行の意図を確認するための注釈行です。
        self.lb_files.delete(0, tk.END)
# [解説 1053] この行の意図を確認するための注釈行です。
        for p in self.file_paths: self.lb_files.insert(tk.END, p)
# [解説 1054] この行の意図を確認するための注釈行です。
        self.lb_files.selection_set(0); self.lb_files.activate(0)
# [解説 1055] この行の意図を確認するための注釈行です。
        self.last_sel_index=0
# [解説 1056] この行の意図を確認するための注釈行です。
        if self.auto_preview.get(): self.on_preview()
# [解説 1057] この行の意図を確認するための注釈行です。
        self._post_status(f"{len(self.file_paths)} 件のファイルを読み込み")
# [解説 1058] この行の意図を確認するための注釈行です。

# [解説 1059] この行の意図を確認するための注釈行です。
    def on_pick_outdir(self):
# [解説 1060] この行の意図を確認するための注釈行です。
        d=filedialog.askdirectory(title="CSVと結果画像の出力先フォルダを選択してください")
# [解説 1061] この行の意図を確認するための注釈行です。
        if d:
# [解説 1062] この行の意図を確認するための注釈行です。
            self.output_dir=d
# [解説 1063] この行の意図を確認するための注釈行です。
            self._sync_cfg_from_vars(); self.cfg.save()
# [解説 1064] この行の意図を確認するための注釈行です。
            self._post_status(f"出力先を設定: {self.output_dir}")
# [解説 1065] この行の意図を確認するための注釈行です。

# [解説 1066] この行の意図を確認するための注釈行です。
    def on_zoom_in(self):
# [解説 1067] この行の意図を確認するための注釈行です。
        self.canvas.zoom_in(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
# [解説 1068] この行の意図を確認するための注釈行です。
    def on_zoom_out(self):
# [解説 1069] この行の意図を確認するための注釈行です。
        self.canvas.zoom_out(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
# [解説 1070] この行の意図を確認するための注釈行です。
    def on_fit(self):
# [解説 1071] この行の意図を確認するための注釈行です。
        self.canvas.fit_to_window(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
# [解説 1072] この行の意図を確認するための注釈行です。
    def on_zoom_100(self):
# [解説 1073] この行の意図を確認するための注釈行です。
        self.canvas.set_zoom_100(); self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
# [解説 1074] この行の意図を確認するための注釈行です。

# [解説 1075] この行の意図を確認するための注釈行です。
    def on_preview(self):
# [解説 1076] この行の意図を確認するための注釈行です。
        try:
# [解説 1077] この行の意図を確認するための注釈行です。
            idx=self.last_sel_index
# [解説 1078] この行の意図を確認するための注釈行です。
            if idx is None:
# [解説 1079] この行の意図を確認するための注釈行です。
                sel=self.lb_files.curselection()
# [解説 1080] この行の意図を確認するための注釈行です。
                if not sel: self._post_status("プレビュー対象が選択されていません"); return
# [解説 1081] この行の意図を確認するための注釈行です。
                idx=sel[0]; self.last_sel_index=idx
# [解説 1082] この行の意図を確認するための注釈行です。
            if not (0<=idx<len(self.file_paths)): self._post_status("有効な画像が選択されていません"); return
# [解説 1083] この行の意図を確認するための注釈行です。
            path=self.file_paths[idx]
# [解説 1084] この行の意図を確認するための注釈行です。
            res=analyze_image(
# [解説 1085] この行の意図を確認するための注釈行です。
                path,
# [解説 1086] この行の意図を確認するための注釈行です。
                trim_ratio_x=self.trim_ratio_x.get(),
# [解説 1087] この行の意図を確認するための注釈行です。
                trim_ratio_y=self.trim_ratio_y.get(),
# [解説 1088] この行の意図を確認するための注釈行です。
                diff_thresh=self.diff_thresh.get(),
# [解説 1089] この行の意図を確認するための注釈行です。
                flip_horizontal=bool(self.flip_horizontal.get()),
# [解説 1090] この行の意図を確認するための注釈行です。
                band_top=self.band_top.get(),
# [解説 1091] この行の意図を確認するための注釈行です。
                band_right=self.band_right.get(),
# [解説 1092] この行の意図を確認するための注釈行です。
                band_bottom=self.band_bottom.get(),
# [解説 1093] この行の意図を確認するための注釈行です。
                corner_exclude_x_px=self.corner_exclude_x_px.get(),
# [解説 1094] この行の意図を確認するための注釈行です。
                corner_exclude_y_px=self.corner_exclude_y_px.get()
# [解説 1095] この行の意図を確認するための注釈行です。
            )
# [解説 1096] この行の意図を確認するための注釈行です。
            self._show_preview(path, res)
# [解説 1097] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1098] この行の意図を確認するための注釈行です。
            traceback.print_exc(); self._post_status(f"[エラー:プレビュー] {e}")
# [解説 1099] この行の意図を確認するための注釈行です。

# [解説 1100] この行の意図を確認するための注釈行です。
    def on_batch_process(self):
# [解説 1101] この行の意図を確認するための注釈行です。
        try:
# [解説 1102] この行の意図を確認するための注釈行です。
            if not self.file_paths:
# [解説 1103] この行の意図を確認するための注釈行です。
                self._post_status("処理する画像が選択されていません"); return
# [解説 1104] この行の意図を確認するための注釈行です。
            csv_path=self._get_result_csv_path()
# [解説 1105] この行の意図を確認するための注釈行です。
            header=["filename","folderpath","trim_ratio_x","trim_ratio_y","diff_thresh","flip_horizontal",
# [解説 1106] この行の意図を確認するための注釈行です。
                    "band_top","band_right","band_bottom","corner_exclude_x_px","corner_exclude_y_px",
# [解説 1107] この行の意図を確認するための注釈行です。
                    "top_angle_deg","side_angle_deg","bottom_angle_deg",
# [解説 1108] この行の意図を確認するための注釈行です。
                    "top_slope","side_slope","bottom_slope",
# [解説 1109] この行の意図を確認するための注釈行です。
                    "ru_area","ru_result","rd_area","rd_result","result_img"]
# [解説 1110] この行の意図を確認するための注釈行です。
            count_ok=0
# [解説 1111] この行の意図を確認するための注釈行です。
            for path in self.file_paths:
# [解説 1112] この行の意図を確認するための注釈行です。
                try:
# [解説 1113] この行の意図を確認するための注釈行です。
                    res=analyze_image(
# [解説 1114] この行の意図を確認するための注釈行です。
                        path,
# [解説 1115] この行の意図を確認するための注釈行です。
                        trim_ratio_x=self.trim_ratio_x.get(),
# [解説 1116] この行の意図を確認するための注釈行です。
                        trim_ratio_y=self.trim_ratio_y.get(),
# [解説 1117] この行の意図を確認するための注釈行です。
                        diff_thresh=self.diff_thresh.get(),
# [解説 1118] この行の意図を確認するための注釈行です。
                        flip_horizontal=bool(self.flip_horizontal.get()),
# [解説 1119] この行の意図を確認するための注釈行です。
                        band_top=self.band_top.get(),
# [解説 1120] この行の意図を確認するための注釈行です。
                        band_right=self.band_right.get(),
# [解説 1121] この行の意図を確認するための注釈行です。
                        band_bottom=self.band_bottom.get(),
# [解説 1122] この行の意図を確認するための注釈行です。
                        corner_exclude_x_px=self.corner_exclude_x_px.get(),
# [解説 1123] この行の意図を確認するための注釈行です。
                        corner_exclude_y_px=self.corner_exclude_y_px.get()
# [解説 1124] この行の意図を確認するための注釈行です。
                    )
# [解説 1125] この行の意図を確認するための注釈行です。
                    out_path=save_result_image(res["img_bgr"], path, self.output_dir)
# [解説 1126] この行の意図を確認するための注釈行です。
                    row=[os.path.basename(path), os.path.dirname(path),
# [解説 1127] この行の意図を確認するための注釈行です。
                         self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
# [解説 1128] この行の意図を確認するための注釈行です。
                         int(bool(self.flip_horizontal.get())),
# [解説 1129] この行の意図を確認するための注釈行です。
                         self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
# [解説 1130] この行の意図を確認するための注釈行です。
                         self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
# [解説 1131] この行の意図を確認するための注釈行です。
                         res["top_angle_deg"], res["side_angle_deg"], res["bottom_angle_deg"],
# [解説 1132] この行の意図を確認するための注釈行です。
                         res["top_slope"], res["side_slope"], res["bottom_slope"],
# [解説 1133] この行の意図を確認するための注釈行です。
                         res["ru_area"], res["ru_result"], res["rd_area"], res["rd_result"],
# [解説 1134] この行の意図を確認するための注釈行です。
                         out_path or ""]
# [解説 1135] この行の意図を確認するための注釈行です。
                    self._append_result_csv(csv_path, header, row)
# [解説 1136] この行の意図を確認するための注釈行です。
                    count_ok+=1
# [解説 1137] この行の意図を確認するための注釈行です。
                except Exception as ie:
# [解説 1138] この行の意図を確認するための注釈行です。
                    traceback.print_exc(); self._post_status(f"[警告] 失敗: {path} : {ie}")
# [解説 1139] この行の意図を確認するための注釈行です。
            self._post_status(f"バッチ完了: {count_ok}件 / CSV: {csv_path}")
# [解説 1140] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1141] この行の意図を確認するための注釈行です。
            traceback.print_exc(); self._post_status(f"[エラー:バッチ処理] {e}")
# [解説 1142] この行の意図を確認するための注釈行です。

# [解説 1143] この行の意図を確認するための注釈行です。
    def _show_preview(self, path, result_dict):
# [解説 1144] この行の意図を確認するための注釈行です。
        bgr=result_dict["img_bgr"]; rgb=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
# [解説 1145] この行の意図を確認するための注釈行です。
        self.canvas.set_image(Image.fromarray(rgb))
# [解説 1146] この行の意図を確認するための注釈行です。
        self.zoom_label.config(text=f"{self.canvas.zoom*100:.0f}%")
# [解説 1147] この行の意図を確認するための注釈行です。
        top_p1, top_p2 = result_dict["top_line"]
# [解説 1148] この行の意図を確認するための注釈行です。
        side_p1, side_p2 = result_dict["side_line"]
# [解説 1149] この行の意図を確認するための注釈行です。
        bottom_p1, bottom_p2 = result_dict["bottom_line"]
# [解説 1150] この行の意図を確認するための注釈行です。
        line=(f"{time.strftime('%H:%M:%S')} | {os.path.basename(path)} | "
# [解説 1151] この行の意図を確認するための注釈行です。
              f"RU={result_dict['ru_result']}({result_dict['ru_area']}) "
# [解説 1152] この行の意図を確認するための注釈行です。
              f"RD={result_dict['rd_result']}({result_dict['rd_area']}) | "
# [解説 1153] この行の意図を確認するための注釈行です。
              f"Top={result_dict['top_angle_deg']:.3f}° "
# [解説 1154] この行の意図を確認するための注釈行です。
              f"{result_dict['side_label']}={result_dict['side_angle_deg']:.3f}° "
# [解説 1155] この行の意図を確認するための注釈行です。
              f"Bottom={result_dict['bottom_angle_deg']:.3f}° | "
# [解説 1156] この行の意図を確認するための注釈行です。
              f"Top線:{top_p1}->{top_p2} "
# [解説 1157] この行の意図を確認するための注釈行です。
              f"{result_dict['side_label']}線:{side_p1}->{side_p2} "
# [解説 1158] この行の意図を確認するための注釈行です。
              f"Bottom線:{bottom_p1}->{bottom_p2} | "
# [解説 1159] この行の意図を確認するための注釈行です。
              f"flip={int(bool(self.flip_horizontal.get()))}")
# [解説 1160] この行の意図を確認するための注釈行です。
        self._result_lines.appendleft(line)
# [解説 1161] この行の意図を確認するための注釈行です。
        def _update_result():
# [解説 1162] この行の意図を確認するための注釈行です。
            self.txt_result.configure(state="normal")
# [解説 1163] この行の意図を確認するための注釈行です。
            self.txt_result.delete("1.0", "end")
# [解説 1164] この行の意図を確認するための注釈行です。
            self.txt_result.insert("1.0", "\n".join(list(self._result_lines)))
# [解説 1165] この行の意図を確認するための注釈行です。
            self.txt_result.configure(state="disabled")
# [解説 1166] この行の意図を確認するための注釈行です。
        try:
# [解説 1167] この行の意図を確認するための注釈行です。
            self.after(0, _update_result)
# [解説 1168] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1169] この行の意図を確認するための注釈行です。
            pass
# [解説 1170] この行の意図を確認するための注釈行です。
        self._post_status("解析結果を更新しました。")
# [解説 1171] この行の意図を確認するための注釈行です。
        self.last_result=result_dict; self.last_result_path=path
# [解説 1172] この行の意図を確認するための注釈行です。

# [解説 1173] この行の意図を確認するための注釈行です。
    # ---------- カメラ共通ヘルパ（スレッド安全） ----------
# [解説 1174] この行の意図を確認するための注釈行です。
    def _cam_open_if_needed(self):
# [解説 1175] この行の意図を確認するための注釈行です。
        with self._cam_lock:
# [解説 1176] この行の意図を確認するための注釈行です。
            if self.basler is None:
# [解説 1177] この行の意図を確認するための注釈行です。
                self.basler = BaslerCamera(device_index=self.var_camera_index.get(), timeout_ms=self.var_timeout_ms.get())
# [解説 1178] この行の意図を確認するための注釈行です。
                self.basler.open()
# [解説 1179] この行の意図を確認するための注釈行です。
            else:
# [解説 1180] この行の意図を確認するための注釈行です。
                if not self.basler.is_healthy():
# [解説 1181] この行の意図を確認するための注釈行です。
                    self.basler.reopen()
# [解説 1182] この行の意図を確認するための注釈行です。
            return self.basler
# [解説 1183] この行の意図を確認するための注釈行です。

# [解説 1184] この行の意図を確認するための注釈行です。
    def _cam_close_and_null(self):
# [解説 1185] この行の意図を確認するための注釈行です。
        with self._cam_lock:
# [解説 1186] この行の意図を確認するための注釈行です。
            try:
# [解説 1187] この行の意図を確認するための注釈行です。
                if self.basler:
# [解説 1188] この行の意図を確認するための注釈行です。
                    self.basler.close()
# [解説 1189] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 1190] この行の意図を確認するための注釈行です。
                pass
# [解説 1191] この行の意図を確認するための注釈行です。
            self.basler = None
# [解説 1192] この行の意図を確認するための注釈行です。

# [解説 1193] この行の意図を確認するための注釈行です。
    def _cam_snap_bgr(self):
# [解説 1194] この行の意図を確認するための注釈行です。
        # 1回目
# [解説 1195] この行の意図を確認するための注釈行です。
        with self._cam_lock:
# [解説 1196] この行の意図を確認するための注釈行です。
            cam = self._cam_open_if_needed()
# [解説 1197] この行の意図を確認するための注釈行です。
            try:
# [解説 1198] この行の意図を確認するための注釈行です。
                return cam.snap_bgr()
# [解説 1199] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 1200] この行の意図を確認するための注釈行です。
                try:
# [解説 1201] この行の意図を確認するための注釈行です。
                    cam.reopen()
# [解説 1202] この行の意図を確認するための注釈行です。
                except Exception:
# [解説 1203] この行の意図を確認するための注釈行です。
                    self.basler = None
# [解説 1204] この行の意図を確認するための注釈行です。
                    raise
# [解説 1205] この行の意図を確認するための注釈行です。
        # 2回目
# [解説 1206] この行の意図を確認するための注釈行です。
        with self._cam_lock:
# [解説 1207] この行の意図を確認するための注釈行です。
            cam = self._cam_open_if_needed()
# [解説 1208] この行の意図を確認するための注釈行です。
            return cam.snap_bgr()
# [解説 1209] この行の意図を確認するための注釈行です。

# [解説 1210] この行の意図を確認するための注釈行です。
    # ---------- 単発撮像/連続Grab ----------
# [解説 1211] この行の意図を確認するための注釈行です。
    def on_capture_basler(self):
# [解説 1212] この行の意図を確認するための注釈行です。
        if self.video_running:
# [解説 1213] この行の意図を確認するための注釈行です。
            self._post_status("連続Grab停止中のみ単発撮像が可能です。先に［連続Grab停止］してください。")
# [解説 1214] この行の意図を確認するための注釈行です。
            return
# [解説 1215] この行の意図を確認するための注釈行です。
        try:
# [解説 1216] この行の意図を確認するための注釈行です。
            if not HAS_PYLYON:
# [解説 1217] この行の意図を確認するための注釈行です。
                self._post_status("pypylon が見つかりません。Basler Pylon と pypylon を導入してください。"); return
# [解説 1218] この行の意図を確認するための注釈行です。
            img_bgr=self._cam_snap_bgr()
# [解説 1219] この行の意図を確認するための注釈行です。
            ts=time.strftime("%Y%m%d_%H%M%S")
# [解説 1220] この行の意図を確認するための注釈行です。
            tmp_path=os.path.join(tempfile.gettempdir(), f"BaslerShot_{ts}.png")
# [解説 1221] この行の意図を確認するための注釈行です。
            ok, buf=cv2.imencode(".png", img_bgr)
# [解説 1222] この行の意図を確認するための注釈行です。
            if not ok: raise RuntimeError("撮像画像のエンコードに失敗")
# [解説 1223] この行の意図を確認するための注釈行です。
            buf.tofile(tmp_path)
# [解説 1224] この行の意図を確認するための注釈行です。
            self._auto_cleanup_temp_files()
# [解説 1225] この行の意図を確認するための注釈行です。
            self.file_paths.append(tmp_path)
# [解説 1226] この行の意図を確認するための注釈行です。
            self.lb_files.insert(tk.END, tmp_path)
# [解説 1227] この行の意図を確認するための注釈行です。
            self.last_sel_index=len(self.file_paths)-1
# [解説 1228] この行の意図を確認するための注釈行です。
            self.lb_files.selection_clear(0, tk.END); self.lb_files.selection_set(tk.END); self.lb_files.activate(tk.END)
# [解説 1229] この行の意図を確認するための注釈行です。
            if self.auto_preview.get(): self.on_preview()
# [解説 1230] この行の意図を確認するための注釈行です。
            self._post_status(f"撮像: {tmp_path}")
# [解説 1231] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1232] この行の意図を確認するための注釈行です。
            traceback.print_exc(); self._post_status(f"[エラー:撮像] {e}")
# [解説 1233] この行の意図を確認するための注釈行です。

# [解説 1234] この行の意図を確認するための注釈行です。
    def on_video_start(self):
# [解説 1235] この行の意図を確認するための注釈行です。
        if self.video_running:
# [解説 1236] この行の意図を確認するための注釈行です。
            self._post_status("すでに連続Grab中です")
# [解説 1237] この行の意図を確認するための注釈行です。
            return
# [解説 1238] この行の意図を確認するための注釈行です。
        if not HAS_PYLYON:
# [解説 1239] この行の意図を確認するための注釈行です。
            self._post_status("pypylon が見つかりません。Basler Pylon と pypylon を導入してください。"); return
# [解説 1240] この行の意図を確認するための注釈行です。
        self.video_stop=False
# [解説 1241] この行の意図を確認するための注釈行です。
        self.video_running=True
# [解説 1242] この行の意図を確認するための注釈行です。
        self.video_thread=threading.Thread(target=self._video_loop, daemon=True)
# [解説 1243] この行の意図を確認するための注釈行です。
        self.video_thread.start()
# [解説 1244] この行の意図を確認するための注釈行です。
        self._post_status("連続Grab開始")
# [解説 1245] この行の意図を確認するための注釈行です。

# [解説 1246] この行の意図を確認するための注釈行です。
    def on_video_stop(self):
# [解説 1247] この行の意図を確認するための注釈行です。
        if not self.video_running:
# [解説 1248] この行の意図を確認するための注釈行です。
            self._post_status("連続Grabは動作していません")
# [解説 1249] この行の意図を確認するための注釈行です。
            return
# [解説 1250] この行の意図を確認するための注釈行です。
        self.video_stop=True
# [解説 1251] この行の意図を確認するための注釈行です。
        if self.video_thread and self.video_thread.is_alive():
# [解説 1252] この行の意図を確認するための注釈行です。
            self.video_thread.join(timeout=1.0)
# [解説 1253] この行の意図を確認するための注釈行です。
        self.video_thread=None
# [解説 1254] この行の意図を確認するための注釈行です。
        self.video_running=False
# [解説 1255] この行の意図を確認するための注釈行です。
        self._post_status("連続Grab停止")
# [解説 1256] この行の意図を確認するための注釈行です。

# [解説 1257] この行の意図を確認するための注釈行です。
    def _video_loop(self):
# [解説 1258] この行の意図を確認するための注釈行です。
        target_fps = 15.0
# [解説 1259] この行の意図を確認するための注釈行です。
        period = 1.0 / target_fps
# [解説 1260] この行の意図を確認するための注釈行です。
        last_log_err = 0.0
# [解説 1261] この行の意図を確認するための注釈行です。
        while not self.video_stop:
# [解説 1262] この行の意図を確認するための注釈行です。
            t0 = time.monotonic()
# [解説 1263] この行の意図を確認するための注釈行です。
            try:
# [解説 1264] この行の意図を確認するための注釈行です。
                img_bgr = self._cam_snap_bgr()
# [解説 1265] この行の意図を確認するための注釈行です。
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
# [解説 1266] この行の意図を確認するための注釈行です。
                pil = Image.fromarray(rgb)
# [解説 1267] この行の意図を確認するための注釈行です。
                self.after(0, lambda im=pil: self.canvas.set_image(im))
# [解説 1268] この行の意図を確認するための注釈行です。
            except Exception as e:
# [解説 1269] この行の意図を確認するための注釈行です。
                if time.monotonic() - last_log_err > 1.5:
# [解説 1270] この行の意図を確認するための注釈行です。
                    self._post_status(f"連続Grab: 撮像エラー: {e}")
# [解説 1271] この行の意図を確認するための注釈行です。
                    last_log_err = time.monotonic()
# [解説 1272] この行の意図を確認するための注釈行です。
                time.sleep(0.2)
# [解説 1273] この行の意図を確認するための注釈行です。
            dt = time.monotonic() - t0
# [解説 1274] この行の意図を確認するための注釈行です。
            if dt < period:
# [解説 1275] この行の意図を確認するための注釈行です。
                time.sleep(max(0.0, period - dt))
# [解説 1276] この行の意図を確認するための注釈行です。

# [解説 1277] この行の意図を確認するための注釈行です。
    # ---------- PLC 接続/監視 ----------
# [解説 1278] この行の意図を確認するための注釈行です。
    def on_plc_connect(self):
# [解説 1279] この行の意図を確認するための注釈行です。
        try:
# [解説 1280] この行の意図を確認するための注釈行です。
            # self.plc が None の場合は再生成してから接続
# [解説 1281] この行の意図を確認するための注釈行です。
            if self.plc is None:
# [解説 1282] この行の意図を確認するための注釈行です。
                self.plc = PLCClient()
# [解説 1283] この行の意図を確認するための注釈行です。
            self.plc.connect(self.var_plc_ip.get().strip(), int(self.var_plc_port.get()))
# [解説 1284] この行の意図を確認するための注釈行です。
            self.plc_connected=True
# [解説 1285] この行の意図を確認するための注釈行です。
            self.manual_disconnected=False
# [解説 1286] この行の意図を確認するための注釈行です。
            self._post_status("PLC接続OK")
# [解説 1287] この行の意図を確認するための注釈行です。
            if self.var_alive_auto.get():
# [解説 1288] この行の意図を確認するための注釈行です。
                self._hb_start_if_needed()
# [解説 1289] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1290] この行の意図を確認するための注釈行です。
            self.plc_connected=False
# [解説 1291] この行の意図を確認するための注釈行です。
            self._post_status(f"[PLC接続エラー] {e}")
# [解説 1292] この行の意図を確認するための注釈行です。

# [解説 1293] この行の意図を確認するための注釈行です。
    def on_plc_disconnect(self):
# [解説 1294] この行の意図を確認するための注釈行です。
        try:
# [解説 1295] この行の意図を確認するための注釈行です。
            self.manual_disconnected=True
# [解説 1296] この行の意図を確認するための注釈行です。
            self.on_plc_watch_stop(manual=True)
# [解説 1297] この行の意図を確認するための注釈行です。
            self._hb_stop()
# [解説 1298] この行の意図を確認するための注釈行です。
            if self.plc:
# [解説 1299] この行の意図を確認するための注釈行です。
                self.plc.close()
# [解説 1300] この行の意図を確認するための注釈行です。
        finally:
# [解説 1301] この行の意図を確認するための注釈行です。
            self.plc_connected=False
# [解説 1302] この行の意図を確認するための注釈行です。
            self._post_status("PLC切断しました")
# [解説 1303] この行の意図を確認するための注釈行です。

# [解説 1304] この行の意図を確認するための注釈行です。
    def on_test_done(self):
# [解説 1305] この行の意図を確認するための注釈行です。
        self._safe_plc(lambda: self.plc.pulse_bit(self.var_dev_done.get().strip(), self.var_done_ms.get()))
# [解説 1306] この行の意図を確認するための注釈行です。

# [解説 1307] この行の意図を確認するための注釈行です。
    def on_clear_errors(self):
# [解説 1308] この行の意図を確認するための注釈行です。
        def _clear():
# [解説 1309] この行の意図を確認するための注釈行です。
            self.plc.write_bit(self.var_dev_err_to.get().strip(), False)
# [解説 1310] この行の意図を確認するための注釈行です。
            self.plc.write_bit(self.var_dev_err_an.get().strip(), False)
# [解説 1311] この行の意図を確認するための注釈行です。
        self._safe_plc(_clear, quiet=True)
# [解説 1312] この行の意図を確認するための注釈行です。
        self._post_status("PLCエラークリア書込み")
# [解説 1313] この行の意図を確認するための注釈行です。

# [解説 1314] この行の意図を確認するための注釈行です。
    def on_plc_watch_start(self):
# [解説 1315] この行の意図を確認するための注釈行です。
        if not self.plc_connected:
# [解説 1316] この行の意図を確認するための注釈行です。
            self._post_status("PLC 未接続です。先に接続してください。"); return
# [解説 1317] この行の意図を確認するための注釈行です。
        if not HAS_PYLYON:
# [解説 1318] この行の意図を確認するための注釈行です。
            self._post_status("pypylon がありません。"); return
# [解説 1319] この行の意図を確認するための注釈行です。
        try:
# [解説 1320] この行の意図を確認するための注釈行です。
            self._cam_open_if_needed()
# [解説 1321] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1322] この行の意図を確認するための注釈行です。
            self._post_status(f"カメラ初期化に失敗: {e}"); return
# [解説 1323] この行の意図を確認するための注釈行です。
        if self.plc_thread and self.plc_thread.is_alive():
# [解説 1324] この行の意図を確認するための注釈行です。
            self._post_status("既に監視中です"); return
# [解説 1325] この行の意図を確認するための注釈行です。
        self.plc_stop=False; self.prev_trig=False
# [解説 1326] この行の意図を確認するための注釈行です。
        self.manual_stopped=False
# [解説 1327] この行の意図を確認するための注釈行です。
        self.plc_thread=threading.Thread(target=self._plc_loop, daemon=True); self.plc_thread.start()
# [解説 1328] この行の意図を確認するための注釈行です。
        self._post_status("トリガ監視開始")
# [解説 1329] この行の意図を確認するための注釈行です。

# [解説 1330] この行の意図を確認するための注釈行です。
    def on_plc_watch_stop(self, manual:bool=True):
# [解説 1331] この行の意図を確認するための注釈行です。
        self.manual_stopped = bool(manual)
# [解説 1332] この行の意図を確認するための注釈行です。
        self.plc_stop=True
# [解説 1333] この行の意図を確認するための注釈行です。
        if self.plc_thread and self.plc_thread.is_alive():
# [解説 1334] この行の意図を確認するための注釈行です。
            self.plc_thread.join(timeout=1.0)
# [解説 1335] この行の意図を確認するための注釈行です。
        self.plc_thread=None
# [解説 1336] この行の意図を確認するための注釈行です。
        self._post_status("トリガ監視停止")
# [解説 1337] この行の意図を確認するための注釈行です。

# [解説 1338] この行の意図を確認するための注釈行です。
    def _plc_loop(self):
# [解説 1339] この行の意図を確認するための注釈行です。
        poll=0.01
# [解説 1340] この行の意図を確認するための注釈行です。
        while not self.plc_stop:
# [解説 1341] この行の意図を確認するための注釈行です。
            try:
# [解説 1342] この行の意図を確認するための注釈行です。
                trig=self.plc.read_bit(self.var_dev_trig.get().strip())
# [解説 1343] この行の意図を確認するための注釈行です。
            except Exception as e:
# [解説 1344] この行の意図を確認するための注釈行です。
                self._post_status(f"PLC読取エラー: {e}")
# [解説 1345] この行の意図を確認するための注釈行です。
                time.sleep(0.2); continue
# [解説 1346] この行の意図を確認するための注釈行です。

# [解説 1347] この行の意図を確認するための注釈行です。
            if trig and not self.prev_trig:
# [解説 1348] この行の意図を確認するための注釈行です。
                self._post_status("トリガ検出: 撮像→解析→返答")
# [解説 1349] この行の意図を確認するための注釈行です。
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_busy.get().strip(), True), quiet=True)
# [解説 1350] この行の意図を確認するための注釈行です。
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_err_to.get().strip(), False), quiet=True)
# [解説 1351] この行の意図を確認するための注釈行です。
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_err_an.get().strip(), False), quiet=True)
# [解説 1352] この行の意図を確認するための注釈行です。

# [解説 1353] この行の意図を確認するための注釈行です。
                ok_capture=True; img_tmp_path=None
# [解説 1354] この行の意図を確認するための注釈行です。
                error_type=None
# [解説 1355] この行の意図を確認するための注釈行です。
                try:
# [解説 1356] この行の意図を確認するための注釈行です。
                    shot_dir = self.cfg.plc_shot_dir if self.cfg.plc_shot_dir else tempfile.gettempdir()
# [解説 1357] この行の意図を確認するための注釈行です。
                    os.makedirs(shot_dir, exist_ok=True)
# [解説 1358] この行の意図を確認するための注釈行です。
                    ts=time.strftime("%Y%m%d_%H%M%S")
# [解説 1359] この行の意図を確認するための注釈行です。
                    img_tmp_path=os.path.join(shot_dir, f"PLCshot_{ts}.png")
# [解説 1360] この行の意図を確認するための注釈行です。

# [解説 1361] この行の意図を確認するための注釈行です。
                    img_bgr = self._cam_snap_bgr()
# [解説 1362] この行の意図を確認するための注釈行です。

# [解説 1363] この行の意図を確認するための注釈行です。
                    ok, buf=cv2.imencode(".png", img_bgr)
# [解説 1364] この行の意図を確認するための注釈行です。
                    if ok:
# [解説 1365] この行の意図を確認するための注釈行です。
                        buf.tofile(img_tmp_path)
# [解説 1366] この行の意図を確認するための注釈行です。
                        self._auto_cleanup_temp_files()
# [解説 1367] この行の意図を確認するための注釈行です。
                    else:
# [解説 1368] この行の意図を確認するための注釈行です。
                        ok_capture=False
# [解説 1369] この行の意図を確認するための注釈行です。
                        error_type="CAPTURE"
# [解説 1370] この行の意図を確認するための注釈行です。
                except Exception as e:
# [解説 1371] この行の意図を確認するための注釈行です。
                    ok_capture=False
# [解説 1372] この行の意図を確認するための注釈行です。
                    msg=str(e).lower()
# [解説 1373] この行の意図を確認するための注釈行です。
                    error_type = "TIMEOUT" if ("timeout" in msg or "time out" in msg) else "CAPTURE"
# [解説 1374] この行の意図を確認するための注釈行です。
                    self._post_status(f"撮像エラー: {e}")
# [解説 1375] この行の意図を確認するための注釈行です。
                    self._cam_close_and_null()
# [解説 1376] この行の意図を確認するための注釈行です。

# [解説 1377] この行の意図を確認するための注釈行です。
                ru_notch=False; rd_notch=False; to_error=False; an_error=False
# [解説 1378] この行の意図を確認するための注釈行です。
                csv_path=self._get_result_csv_path()
# [解説 1379] この行の意図を確認するための注釈行です。
                header=["filename","folderpath","trim_ratio_x","trim_ratio_y","diff_thresh","flip_horizontal",
# [解説 1380] この行の意図を確認するための注釈行です。
                        "band_top","band_right","band_bottom","corner_exclude_x_px","corner_exclude_y_px",
# [解説 1381] この行の意図を確認するための注釈行です。
                        "top_angle_deg","side_angle_deg","bottom_angle_deg",
# [解説 1382] この行の意図を確認するための注釈行です。
                        "top_slope","side_slope","bottom_slope",
# [解説 1383] この行の意図を確認するための注釈行です。
                        "ru_area","ru_result","rd_area","rd_result","result_img"]
# [解説 1384] この行の意図を確認するための注釈行です。

# [解説 1385] この行の意図を確認するための注釈行です。
                if ok_capture and img_tmp_path:
# [解説 1386] この行の意図を確認するための注釈行です。
                    try:
# [解説 1387] この行の意図を確認するための注釈行です。
                        res=analyze_image(
# [解説 1388] この行の意図を確認するための注釈行です。
                            img_tmp_path,
# [解説 1389] この行の意図を確認するための注釈行です。
                            trim_ratio_x=self.trim_ratio_x.get(),
# [解説 1390] この行の意図を確認するための注釈行です。
                            trim_ratio_y=self.trim_ratio_y.get(),
# [解説 1391] この行の意図を確認するための注釈行です。
                            diff_thresh=self.diff_thresh.get(),
# [解説 1392] この行の意図を確認するための注釈行です。
                            flip_horizontal=bool(self.flip_horizontal.get()),
# [解説 1393] この行の意図を確認するための注釈行です。
                            band_top=self.band_top.get(),
# [解説 1394] この行の意図を確認するための注釈行です。
                            band_right=self.band_right.get(),
# [解説 1395] この行の意図を確認するための注釈行です。
                            band_bottom=self.band_bottom.get(),
# [解説 1396] この行の意図を確認するための注釈行です。
                            corner_exclude_x_px=self.corner_exclude_x_px.get(),
# [解説 1397] この行の意図を確認するための注釈行です。
                            corner_exclude_y_px=self.corner_exclude_y_px.get()
# [解説 1398] この行の意図を確認するための注釈行です。
                        )
# [解説 1399] この行の意図を確認するための注釈行です。
                        ru_notch=(res["ru_result"]=="NOTCH"); rd_notch=(res["rd_result"]=="NOTCH")
# [解説 1400] この行の意図を確認するための注釈行です。
                        self._post_preview(img_tmp_path, res)
# [解説 1401] この行の意図を確認するための注釈行です。
                        self.file_paths.append(img_tmp_path); self._post_list_add(img_tmp_path)
# [解説 1402] この行の意図を確認するための注釈行です。

# [解説 1403] この行の意図を確認するための注釈行です。
                        result_img_path = save_result_image(res["img_bgr"], img_tmp_path, self.output_dir or os.path.dirname(img_tmp_path))
# [解説 1404] この行の意図を確認するための注釈行です。
                        row=[os.path.basename(img_tmp_path), os.path.dirname(img_tmp_path),
# [解説 1405] この行の意図を確認するための注釈行です。
                             self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
# [解説 1406] この行の意図を確認するための注釈行です。
                             int(bool(self.flip_horizontal.get())),
# [解説 1407] この行の意図を確認するための注釈行です。
                             self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
# [解説 1408] この行の意図を確認するための注釈行です。
                             self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
# [解説 1409] この行の意図を確認するための注釈行です。
                             res["top_angle_deg"], res["side_angle_deg"], res["bottom_angle_deg"],
# [解説 1410] この行の意図を確認するための注釈行です。
                             res["top_slope"], res["side_slope"], res["bottom_slope"],
# [解説 1411] この行の意図を確認するための注釈行です。
                             res["ru_area"], res["ru_result"], res["rd_area"], res["rd_result"],
# [解説 1412] この行の意図を確認するための注釈行です。
                             result_img_path or ""]
# [解説 1413] この行の意図を確認するための注釈行です。
                        self._append_result_csv(csv_path, header, row)
# [解説 1414] この行の意図を確認するための注釈行です。
                    except Exception as e:
# [解説 1415] この行の意図を確認するための注釈行です。
                        an_error=True
# [解説 1416] この行の意図を確認するための注釈行です。
                        self._post_status(f"解析エラー: {e}")
# [解説 1417] この行の意図を確認するための注釈行です。
                        row=[os.path.basename(img_tmp_path) if img_tmp_path else "",
# [解説 1418] この行の意図を確認するための注釈行です。
                             os.path.dirname(img_tmp_path) if img_tmp_path else "",
# [解説 1419] この行の意図を確認するための注釈行です。
                             self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
# [解説 1420] この行の意図を確認するための注釈行です。
                             int(bool(self.flip_horizontal.get())),
# [解説 1421] この行の意図を確認するための注釈行です。
                             self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
# [解説 1422] この行の意図を確認するための注釈行です。
                             self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
# [解説 1423] この行の意図を確認するための注釈行です。
                             "", "", "", "", "", "",
# [解説 1424] この行の意図を確認するための注釈行です。
                             -1, "ERROR_ANALYZE", -1, "ERROR_ANALYZE", ""]
# [解説 1425] この行の意図を確認するための注釈行です。
                        self._append_result_csv(csv_path, header, row)
# [解説 1426] この行の意図を確認するための注釈行です。
                else:
# [解説 1427] この行の意図を確認するための注釈行です。
                    to_error=True
# [解説 1428] この行の意図を確認するための注釈行です。
                    row=["", self.cfg.plc_shot_dir or tempfile.gettempdir(),
# [解説 1429] この行の意図を確認するための注釈行です。
                         self.trim_ratio_x.get(), self.trim_ratio_y.get(), self.diff_thresh.get(),
# [解説 1430] この行の意図を確認するための注釈行です。
                         int(bool(self.flip_horizontal.get())),
# [解説 1431] この行の意図を確認するための注釈行です。
                         self.band_top.get(), self.band_right.get(), self.band_bottom.get(),
# [解説 1432] この行の意図を確認するための注釈行です。
                         self.corner_exclude_x_px.get(), self.corner_exclude_y_px.get(),
# [解説 1433] この行の意図を確認するための注釈行です。
                         "", "", "", "", "", "",
# [解説 1434] この行の意図を確認するための注釈行です。
                         -1, "ERROR_TIMEOUT" if (error_type=="TIMEOUT") else "ERROR_CAPTURE",
# [解説 1435] この行の意図を確認するための注釈行です。
                         -1, "ERROR_TIMEOUT" if (error_type=="TIMEOUT") else "ERROR_CAPTURE",
# [解説 1436] この行の意図を確認するための注釈行です。
                         ""]
# [解説 1437] この行の意図を確認するための注釈行です。
                    self._append_result_csv(csv_path, header, row)
# [解説 1438] この行の意図を確認するための注釈行です。

# [解説 1439] この行の意図を確認するための注釈行です。
                # PLCへ返答
# [解説 1440] この行の意図を確認するための注釈行です。
                try:
# [解説 1441] この行の意図を確認するための注釈行です。
                    self.plc.write_bit(self.var_dev_ru.get().strip(), bool(ru_notch))
# [解説 1442] この行の意図を確認するための注釈行です。
                    self.plc.write_bit(self.var_dev_rd.get().strip(), bool(rd_notch))
# [解説 1443] この行の意図を確認するための注釈行です。
                    if to_error: self.plc.write_bit(self.var_dev_err_to.get().strip(), True)
# [解説 1444] この行の意図を確認するための注釈行です。
                    if an_error: self.plc.write_bit(self.var_dev_err_an.get().strip(), True)
# [解説 1445] この行の意図を確認するための注釈行です。
                except Exception as e:
# [解説 1446] この行の意図を確認するための注釈行です。
                    self._post_status(f"結果/エラー書込エラー: {e}")
# [解説 1447] この行の意図を確認するための注釈行です。

# [解説 1448] この行の意図を確認するための注釈行です。
                # 完了パルス
# [解説 1449] この行の意図を確認するための注釈行です。
                try:
# [解説 1450] この行の意図を確認するための注釈行です。
                    self.plc.pulse_bit(self.var_dev_done.get().strip(), self.var_done_ms.get())
# [解説 1451] この行の意図を確認するための注釈行です。
                except Exception as e:
# [解説 1452] この行の意図を確認するための注釈行です。
                    self._post_status(f"完了パルスエラー: {e}")
# [解説 1453] この行の意図を確認するための注釈行です。

# [解説 1454] この行の意図を確認するための注釈行です。
                self._safe_plc(lambda: self.plc.write_bit(self.var_dev_busy.get().strip(), False), quiet=True)
# [解説 1455] この行の意図を確認するための注釈行です。
                self._post_status(f"返答: RU={int(ru_notch)} RD={int(rd_notch)} TO_ERR={int(to_error)} AN_ERR={int(an_error)}")
# [解説 1456] この行の意図を確認するための注釈行です。

# [解説 1457] この行の意図を確認するための注釈行です。
            self.prev_trig=trig
# [解説 1458] この行の意図を確認するための注釈行です。
            time.sleep(poll)
# [解説 1459] この行の意図を確認するための注釈行です。

# [解説 1460] この行の意図を確認するための注釈行です。
    # ---------- ハートビート ----------
# [解説 1461] この行の意図を確認するための注釈行です。
    def _hb_start_if_needed(self):
# [解説 1462] この行の意図を確認するための注釈行です。
        if not self.plc_connected: return
# [解説 1463] この行の意図を確認するための注釈行です。
        if not self.var_alive_auto.get(): return
# [解説 1464] この行の意図を確認するための注釈行です。
        if self.hb_thread and self.hb_thread.is_alive(): return
# [解説 1465] この行の意図を確認するための注釈行です。
        self.hb_stop=False
# [解説 1466] この行の意図を確認するための注釈行です。
        try:
# [解説 1467] この行の意図を確認するための注釈行です。
            self.hb_value=self.plc.read_word(self.var_dev_alive.get().strip())
# [解説 1468] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1469] この行の意図を確認するための注釈行です。
            self.hb_value=0
# [解説 1470] この行の意図を確認するための注釈行です。
        self.hb_thread=threading.Thread(target=self._hb_loop, daemon=True); self.hb_thread.start()
# [解説 1471] この行の意図を確認するための注釈行です。
        self._post_status("HB自動開始")
# [解説 1472] この行の意図を確認するための注釈行です。

# [解説 1473] この行の意図を確認するための注釈行です。
    def _hb_stop(self):
# [解説 1474] この行の意図を確認するための注釈行です。
        self.hb_stop=True
# [解説 1475] この行の意図を確認するための注釈行です。
        if self.hb_thread and self.hb_thread.is_alive():
# [解説 1476] この行の意図を確認するための注釈行です。
            self.hb_thread.join(timeout=1.0)
# [解説 1477] この行の意図を確認するための注釈行です。
        self.hb_thread=None
# [解説 1478] この行の意図を確認するための注釈行です。
        self._post_status("HB停止")
# [解説 1479] この行の意図を確認するための注釈行です。

# [解説 1480] この行の意図を確認するための注釈行です。
    def _hb_loop(self):
# [解説 1481] この行の意図を確認するための注釈行です。
        last_err=0.0
# [解説 1482] この行の意図を確認するための注釈行です。
        while not self.hb_stop:
# [解説 1483] この行の意図を確認するための注釈行です。
            if not self.plc_connected:
# [解説 1484] この行の意図を確認するための注釈行です。
                time.sleep(0.5); continue
# [解説 1485] この行の意図を確認するための注釈行です。
            try:
# [解説 1486] この行の意図を確認するための注釈行です。
                interval=max(10, int(self.var_alive_ms.get()))
# [解説 1487] この行の意図を確認するための注釈行です。
                step=max(1, int(self.var_alive_step.get()))
# [解説 1488] この行の意図を確認するための注釈行です。
                self.hb_value=(self.hb_value+step)&0xFFFF
# [解説 1489] この行の意図を確認するための注釈行です。
                self.plc.write_word(self.var_dev_alive.get().strip(), self.hb_value)
# [解説 1490] この行の意図を確認するための注釈行です。
            except Exception as e:
# [解説 1491] この行の意図を確認するための注釈行です。
                now=time.monotonic()
# [解説 1492] この行の意図を確認するための注釈行です。
                if now-last_err>1.5:
# [解説 1493] この行の意図を確認するための注釈行です。
                    self._post_status(f"HB書込エラー: {e}")
# [解説 1494] この行の意図を確認するための注釈行です。
                    last_err=now
# [解説 1495] この行の意図を確認するための注釈行です。
            time.sleep(max(10, int(self.var_alive_ms.get()))/1000.0)
# [解説 1496] この行の意図を確認するための注釈行です。

# [解説 1497] この行の意図を確認するための注釈行です。
    # ---------- 自動再接続マネージャ ----------
# [解説 1498] この行の意図を確認するための注釈行です。
    def _auto_manager_start(self):
# [解説 1499] この行の意図を確認するための注釈行です。
        threading.Thread(target=self._auto_manager_loop, daemon=True).start()
# [解説 1500] この行の意図を確認するための注釈行です。

# [解説 1501] この行の意図を確認するための注釈行です。
    def _auto_manager_loop(self):
# [解説 1502] この行の意図を確認するための注釈行です。
        plc_backoff=1.0; cam_backoff=1.0
# [解説 1503] この行の意図を確認するための注釈行です。
        while True:
# [解説 1504] この行の意図を確認するための注釈行です。
            try:
# [解説 1505] この行の意図を確認するための注釈行です。
                if self.cfg.auto_reconnect and not self.manual_disconnected:
# [解説 1506] この行の意図を確認するための注釈行です。
                    # PLC 自動接続
# [解説 1507] この行の意図を確認するための注釈行です。
                    if not self.plc_connected:
# [解説 1508] この行の意図を確認するための注釈行です。
                        try:
# [解説 1509] この行の意図を確認するための注釈行です。
                            self.on_plc_connect()
# [解説 1510] この行の意図を確認するための注釈行です。
                            plc_backoff=1.0
# [解説 1511] この行の意図を確認するための注釈行です。
                        except Exception as e:
# [解説 1512] この行の意図を確認するための注釈行です。
                            self._post_status(f"自動PLC接続失敗: {e}")
# [解説 1513] この行の意図を確認するための注釈行です。
                            plc_backoff=min(plc_backoff*1.5, 10.0)
# [解説 1514] この行の意図を確認するための注釈行です。
                            time.sleep(plc_backoff)
# [解説 1515] この行の意図を確認するための注釈行です。

# [解説 1516] この行の意図を確認するための注釈行です。
                    # カメラ（連続Grab中は触らない）
# [解説 1517] この行の意図を確認するための注釈行です。
                    if self.plc_connected:
# [解説 1518] この行の意図を確認するための注釈行です。
                        if self.video_running:
# [解説 1519] この行の意図を確認するための注釈行です。
                            pass
# [解説 1520] この行の意図を確認するための注釈行です。
                        else:
# [解説 1521] この行の意図を確認するための注釈行です。
                            need_cam=False
# [解説 1522] この行の意図を確認するための注釈行です。
                            if not HAS_PYLYON:
# [解説 1523] この行の意図を確認するための注釈行です。
                                self._post_status("pypylon 未導入のためカメラ自動接続不可")
# [解説 1524] この行の意図を確認するための注釈行です。
                            else:
# [解説 1525] この行の意図を確認するための注釈行です。
                                with self._cam_lock:
# [解説 1526] この行の意図を確認するための注釈行です。
                                    if self.basler is None:
# [解説 1527] この行の意図を確認するための注釈行です。
                                        need_cam=True
# [解説 1528] この行の意図を確認するための注釈行です。
                                    else:
# [解説 1529] この行の意図を確認するための注釈行です。
                                        try:
# [解説 1530] この行の意図を確認するための注釈行です。
                                            if not self.basler.is_healthy():
# [解説 1531] この行の意図を確認するための注釈行です。
                                                need_cam=True
# [解説 1532] この行の意図を確認するための注釈行です。
                                        except Exception:
# [解説 1533] この行の意図を確認するための注釈行です。
                                            need_cam=True
# [解説 1534] この行の意図を確認するための注釈行です。
                                if need_cam:
# [解説 1535] この行の意図を確認するための注釈行です。
                                    try:
# [解説 1536] この行の意図を確認するための注釈行です。
                                        self._cam_open_if_needed()
# [解説 1537] この行の意図を確認するための注釈行です。
                                        cam_backoff=1.0
# [解説 1538] この行の意図を確認するための注釈行です。
                                        self._post_status("カメラ接続OK")
# [解説 1539] この行の意図を確認するための注釈行です。
                                    except Exception as e:
# [解説 1540] この行の意図を確認するための注釈行です。
                                        self._cam_close_and_null()
# [解説 1541] この行の意図を確認するための注釈行です。
                                        self._post_status(f"カメラ接続失敗: {e}")
# [解説 1542] この行の意図を確認するための注釈行です。
                                        cam_backoff=min(cam_backoff*1.5, 10.0)
# [解説 1543] この行の意図を確認するための注釈行です。
                                        time.sleep(cam_backoff)
# [解説 1544] この行の意図を確認するための注釈行です。

# [解説 1545] この行の意図を確認するための注釈行です。
                    # READY なら監視を自動開始（手動停止していないとき）
# [解説 1546] この行の意図を確認するための注釈行です。
                    if self.plc_connected and (self.basler is not None) and self.cfg.auto_watch_on_ready and not self.manual_stopped:
# [解説 1547] この行の意図を確認するための注釈行です。
                        if not (self.plc_thread and self.plc_thread.is_alive()):
# [解説 1548] この行の意図を確認するための注釈行です。
                            self.on_plc_watch_start()
# [解説 1549] この行の意図を確認するための注釈行です。

# [解説 1550] この行の意図を確認するための注釈行です。
                # 監視中の断検知（PLC）
# [解説 1551] この行の意図を確認するための注釈行です。
                if self.plc_thread and self.plc_thread.is_alive():
# [解説 1552] この行の意図を確認するための注釈行です。
                    try:
# [解説 1553] この行の意図を確認するための注釈行です。
                        _ = self.plc.read_bit(self.var_dev_trig.get().strip())
# [解説 1554] この行の意図を確認するための注釈行です。
                    except Exception as e:
# [解説 1555] この行の意図を確認するための注釈行です。
                        self._post_status(f"PLC通信断検知: {e}")
# [解説 1556] この行の意図を確認するための注釈行です。
                        self._hb_stop()
# [解説 1557] この行の意図を確認するための注釈行です。
                        self.on_plc_watch_stop(manual=False)
# [解説 1558] この行の意図を確認するための注釈行です。
                        try:
# [解説 1559] この行の意図を確認するための注釈行です。
                            if self.plc: self.plc.close()
# [解説 1560] この行の意図を確認するための注釈行です。
                        except: pass
# [解説 1561] この行の意図を確認するための注釈行です。
                        self.plc_connected=False
# [解説 1562] この行の意図を確認するための注釈行です。
                time.sleep(0.8)
# [解説 1563] この行の意図を確認するための注釈行です。
            except Exception as e:
# [解説 1564] この行の意図を確認するための注釈行です。
                self._post_status(f"[Auto] 例外: {e}")
# [解説 1565] この行の意図を確認するための注釈行です。
                time.sleep(1.0)
# [解説 1566] この行の意図を確認するための注釈行です。

# [解説 1567] この行の意図を確認するための注釈行です。
    # ---------- ステータス/スレッド安全UI ----------
# [解説 1568] この行の意図を確認するための注釈行です。
    def _post_status(self, text):
# [解説 1569] この行の意図を確認するための注釈行です。
        stamp=f"{time.strftime('%H:%M:%S')} | {text}"
# [解説 1570] この行の意図を確認するための注釈行です。
        self._log_lines.appendleft(stamp)
# [解説 1571] この行の意図を確認するための注釈行です。
        def _update():
# [解説 1572] この行の意図を確認するための注釈行です。
            self.txt_log.configure(state="normal")
# [解説 1573] この行の意図を確認するための注釈行です。
            self.txt_log.delete("1.0", "end")
# [解説 1574] この行の意図を確認するための注釈行です。
            self.txt_log.insert("1.0", "\n".join(list(self._log_lines)))
# [解説 1575] この行の意図を確認するための注釈行です。
            self.txt_log.configure(state="disabled")
# [解説 1576] この行の意図を確認するための注釈行です。
        try:
# [解説 1577] この行の意図を確認するための注釈行です。
            self.after(0, _update)
# [解説 1578] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1579] この行の意図を確認するための注釈行です。
            pass
# [解説 1580] この行の意図を確認するための注釈行です。

# [解説 1581] この行の意図を確認するための注釈行です。
    def _post_preview(self, path, resdict):
# [解説 1582] この行の意図を確認するための注釈行です。
        try:
# [解説 1583] この行の意図を確認するための注釈行です。
            self.after(0, lambda: self._show_preview(path, resdict))
# [解説 1584] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1585] この行の意図を確認するための注釈行です。
            pass
# [解説 1586] この行の意図を確認するための注釈行です。

# [解説 1587] この行の意図を確認するための注釈行です。
    def _post_list_add(self, path):
# [解説 1588] この行の意図を確認するための注釈行です。
        try:
# [解説 1589] この行の意図を確認するための注釈行です。
            self.after(0, lambda: (self.lb_files.insert(tk.END, path),
# [解説 1590] この行の意図を確認するための注釈行です。
                                   self.lb_files.selection_clear(0, tk.END),
# [解説 1591] この行の意図を確認するための注釈行です。
                                   self.lb_files.selection_set(tk.END)))
# [解説 1592] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1593] この行の意図を確認するための注釈行です。
            pass
# [解説 1594] この行の意図を確認するための注釈行です。

# [解説 1595] この行の意図を確認するための注釈行です。
    def _safe_plc(self, func, quiet=False):
# [解説 1596] この行の意図を確認するための注釈行です。
        try:
# [解説 1597] この行の意図を確認するための注釈行です。
            func()
# [解説 1598] この行の意図を確認するための注釈行です。
            if not quiet: self._post_status("PLC OK")
# [解説 1599] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1600] この行の意図を確認するための注釈行です。
            if not quiet: self._post_status(f"[PLCエラー] {e}")
# [解説 1601] この行の意図を確認するための注釈行です。

# [解説 1602] この行の意図を確認するための注釈行です。
    # ---------- 結果CSVユーティリティ（最大レコード数ローテーション） ----------
# [解説 1603] この行の意図を確認するための注釈行です。
    def _get_result_csv_path(self):
# [解説 1604] この行の意図を確認するための注釈行です。
        base = self.output_dir if self.output_dir else (self.cfg.plc_shot_dir or tempfile.gettempdir())
# [解説 1605] この行の意図を確認するための注釈行です。
        os.makedirs(base, exist_ok=True)
# [解説 1606] この行の意図を確認するための注釈行です。
        return os.path.join(base, "result.csv")
# [解説 1607] この行の意図を確認するための注釈行です。

# [解説 1608] この行の意図を確認するための注釈行です。
    def _append_result_csv(self, csv_path, header, row):
# [解説 1609] この行の意図を確認するための注釈行です。
        max_records = max(1, int(self.csv_max_records.get()))
# [解説 1610] この行の意図を確認するための注釈行です。
        rows=[]
# [解説 1611] この行の意図を確認するための注釈行です。
        if os.path.isfile(csv_path):
# [解説 1612] この行の意図を確認するための注釈行です。
            try:
# [解説 1613] この行の意図を確認するための注釈行です。
                with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
# [解説 1614] この行の意図を確認するための注釈行です。
                    r=csv.reader(f)
# [解説 1615] この行の意図を確認するための注釈行です。
                    existing=list(r)
# [解説 1616] この行の意図を確認するための注釈行です。
                if existing:
# [解説 1617] この行の意図を確認するための注釈行です。
                    if existing[0]==header:
# [解説 1618] この行の意図を確認するための注釈行です。
                        rows=existing[1:]
# [解説 1619] この行の意図を確認するための注釈行です。
                    else:
# [解説 1620] この行の意図を確認するための注釈行です。
                        rows=existing
# [解説 1621] この行の意図を確認するための注釈行です。
            except Exception:
# [解説 1622] この行の意図を確認するための注釈行です。
                rows=[]
# [解説 1623] この行の意図を確認するための注釈行です。
        rows.append([*row])
# [解説 1624] この行の意図を確認するための注釈行です。
        if len(rows)>max_records:
# [解説 1625] この行の意図を確認するための注釈行です。
            rows = rows[-max_records:]
# [解説 1626] この行の意図を確認するための注釈行です。
        d=os.path.dirname(csv_path)
# [解説 1627] この行の意図を確認するための注釈行です。
        if d: os.makedirs(d, exist_ok=True)
# [解説 1628] この行の意図を確認するための注釈行です。
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
# [解説 1629] この行の意図を確認するための注釈行です。
            w=csv.writer(f)
# [解説 1630] この行の意図を確認するための注釈行です。
            w.writerow(header)
# [解説 1631] この行の意図を確認するための注釈行です。
            w.writerows(rows)
# [解説 1632] この行の意図を確認するための注釈行です。

# [解説 1633] この行の意図を確認するための注釈行です。
    # ---------- 一時ファイル清掃 ----------
# [解説 1634] この行の意図を確認するための注釈行です。
    def _auto_cleanup_temp_files(self):
# [解説 1635] この行の意図を確認するための注釈行です。
        try:
# [解説 1636] この行の意図を確認するための注釈行です。
            max_files=int(self.temp_max_files.get())
# [解説 1637] この行の意図を確認するための注釈行です。
            if max_files<=0: return
# [解説 1638] この行の意図を確認するための注釈行です。
            patterns=[os.path.join(tempfile.gettempdir(), f"{p}*.png") for p in self.cfg.temp_prefixes]
# [解説 1639] この行の意図を確認するための注釈行です。
            files=[]
# [解説 1640] この行の意図を確認するための注釈行です。
            for pat in patterns:
# [解説 1641] この行の意図を確認するための注釈行です。
                files.extend(glob.glob(pat))
# [解説 1642] この行の意図を確認するための注釈行です。
            files=sorted(files, key=lambda p: os.path.getmtime(p))
# [解説 1643] この行の意図を確認するための注釈行です。
            if len(files)>max_files:
# [解説 1644] この行の意図を確認するための注釈行です。
                remove=files[0:len(files)-max_files]
# [解説 1645] この行の意図を確認するための注釈行です。
                for f in remove:
# [解説 1646] この行の意図を確認するための注釈行です。
                    try: os.remove(f)
# [解説 1647] この行の意図を確認するための注釈行です。
                    except Exception: pass
# [解説 1648] この行の意図を確認するための注釈行です。
                self._post_status(f"一時ファイル清掃: {len(remove)} 件削除（上限 {max_files}）")
# [解説 1649] この行の意図を確認するための注釈行です。
        except Exception as e:
# [解説 1650] この行の意図を確認するための注釈行です。
            self._post_status(f"[Temp清掃エラー] {e}")
# [解説 1651] この行の意図を確認するための注釈行です。

# [解説 1652] この行の意図を確認するための注釈行です。
    # ---------- 終了 ----------
# [解説 1653] この行の意図を確認するための注釈行です。
    def destroy(self):
# [解説 1654] この行の意図を確認するための注釈行です。
        try:
# [解説 1655] この行の意図を確認するための注釈行です。
            self.on_plc_watch_stop(manual=True)
# [解説 1656] この行の意図を確認するための注釈行です。
            self._hb_stop()
# [解説 1657] この行の意図を確認するための注釈行です。
            if self.plc_connected and self.plc:
# [解説 1658] この行の意図を確認するための注釈行です。
                try: self.plc.close()
# [解説 1659] この行の意図を確認するための注釈行です。
                except: pass
# [解説 1660] この行の意図を確認するための注釈行です。
            if self.basler is not None:
# [解説 1661] この行の意図を確認するための注釈行です。
                try: self.basler.close()
# [解説 1662] この行の意図を確認するための注釈行です。
                except: pass
# [解説 1663] この行の意図を確認するための注釈行です。
            self._sync_cfg_from_vars(); self.cfg.save()
# [解説 1664] この行の意図を確認するための注釈行です。
        except Exception:
# [解説 1665] この行の意図を確認するための注釈行です。
            pass
# [解説 1666] この行の意図を確認するための注釈行です。
        super().destroy()
# [解説 1667] この行の意図を確認するための注釈行です。

# [解説 1668] この行の意図を確認するための注釈行です。

# [解説 1669] この行の意図を確認するための注釈行です。
if __name__ == "__main__":
# [解説 1670] この行の意図を確認するための注釈行です。
    app=NotchApp()
# [解説 1671] この行の意図を確認するための注釈行です。
    app.mainloop()
