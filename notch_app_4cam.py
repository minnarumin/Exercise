# -*- coding: utf-8 -*-
"""
4カメラ版 ガラス基板ノッチ判定ツール
- 共通PLCトリガで4台のカメラを順次撮像・解析
- カメラごとに解析パラメータを設定可能
- 判定結果RU/RDはカメラごとに別デバイスへ書込み
"""

import os
import json
import time
import threading
import tempfile
from datetime import datetime
from dataclasses import dataclass, asdict, field

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from notch_app import (
    analyze_image,
    BaslerCamera,
    PLCClient,
    HAS_PYLYON,
    HAS_PYMC,
)


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

    cams: list[CameraParam] = field(default_factory=lambda: [CameraParam() for _ in range(4)])

    @staticmethod
    def load():
        try:
            with open(CONFIG_PATH_4CAM, "r", encoding="utf-8") as f:
                data = json.load(f)
            cams = [CameraParam(**x) for x in data.get("cams", [])]
            if len(cams) < 4:
                cams.extend([CameraParam() for _ in range(4 - len(cams))])
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

        self.cameras = [None, None, None, None]
        self._cam_locks = [threading.RLock() for _ in range(4)]

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
            })

        self._build_ui()
        self._bind_traces()
        self._post_status("起動完了")

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        top = ttk.Labelframe(root, text="PLC共通設定", padding=8)
        top.pack(fill="x")

        r1 = ttk.Frame(top); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="IP").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_plc_ip, width=16).pack(side="left", padx=4)
        ttk.Label(r1, text="Port").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_plc_port, width=8).pack(side="left", padx=4)
        ttk.Label(r1, text="Trig").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_dev_trig, width=10).pack(side="left", padx=4)

        r2 = ttk.Frame(top); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="DONE").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_done, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="BUSY").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_busy, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="ERR_TO").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_err_to, width=10).pack(side="left", padx=4)
        ttk.Label(r2, text="ERR_AN").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_dev_err_an, width=10).pack(side="left", padx=4)

        r3 = ttk.Frame(top); r3.pack(fill="x", pady=2)
        ttk.Checkbutton(r3, text="SWトリガ", variable=self.var_use_sw_trig).pack(side="left")
        ttk.Label(r3, text="Timeout[ms]").pack(side="left", padx=(10, 2))
        ttk.Entry(r3, textvariable=self.var_timeout_ms, width=8).pack(side="left")
        ttk.Label(r3, text="DONE幅[ms]").pack(side="left", padx=(10, 2))
        ttk.Entry(r3, textvariable=self.var_done_ms, width=8).pack(side="left")
        ttk.Checkbutton(r3, text="自動再接続", variable=self.var_auto_reconnect).pack(side="left", padx=(12, 0))

        r4 = ttk.Frame(top); r4.pack(fill="x", pady=2)
        ttk.Label(r4, text="出力先").pack(side="left")
        ttk.Entry(r4, textvariable=self.var_output_dir, width=45).pack(side="left", padx=4)
        ttk.Label(r4, text="PLC保存先").pack(side="left")
        ttk.Entry(r4, textvariable=self.var_plc_shot_dir, width=30).pack(side="left", padx=4)

        ops = ttk.Frame(root)
        ops.pack(fill="x", pady=(8, 4))
        ttk.Button(ops, text="PLC接続", command=self.on_plc_connect, bootstyle=SUCCESS).pack(side="left")
        ttk.Button(ops, text="PLC切断", command=self.on_plc_disconnect).pack(side="left", padx=4)
        ttk.Button(ops, text="監視開始", command=self.on_watch_start, bootstyle=PRIMARY).pack(side="left", padx=4)
        ttk.Button(ops, text="監視停止", command=self.on_watch_stop).pack(side="left")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)
        for i, v in enumerate(self.cam_vars, start=1):
            frm = ttk.Frame(nb, padding=8)
            nb.add(frm, text=f"Cam{i}")
            self._build_cam_tab(frm, v)

        self.txt_status = tk.Text(root, height=8, wrap="word", state="disabled")
        self.txt_status.pack(fill="x", pady=(6, 0))

    def _build_cam_tab(self, parent, v):
        r1 = ttk.Frame(parent); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="カメラインデックス").pack(side="left")
        ttk.Entry(r1, textvariable=v["camera_index"], width=6).pack(side="left", padx=4)
        ttk.Checkbutton(r1, text="左右反転", variable=v["flip_horizontal"]).pack(side="left", padx=10)

        r2 = ttk.Frame(parent); r2.pack(fill="x", pady=2)
        for key, label, w in [
            ("trim_ratio_x", "trim_x", 6), ("trim_ratio_y", "trim_y", 6), ("diff_thresh", "th", 8),
            ("band_top", "band_top", 6), ("band_right", "band_right", 6), ("band_bottom", "band_bottom", 6),
            ("corner_exclude_x_px", "ex_x", 6), ("corner_exclude_y_px", "ex_y", 6)
        ]:
            ttk.Label(r2, text=label).pack(side="left")
            ttk.Entry(r2, textvariable=v[key], width=w).pack(side="left", padx=2)

        r3 = ttk.Frame(parent); r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="結果RUデバイス").pack(side="left")
        ttk.Entry(r3, textvariable=v["dev_ru"], width=12).pack(side="left", padx=4)
        ttk.Label(r3, text="結果RDデバイス").pack(side="left")
        ttk.Entry(r3, textvariable=v["dev_rd"], width=12).pack(side="left", padx=4)

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
            ))
        self.cfg.cams = cams

    def _post_status(self, text):
        line = f"{time.strftime('%H:%M:%S')} | {text}"
        self.txt_status.configure(state="normal")
        self.txt_status.insert("1.0", line + "\n")
        self.txt_status.configure(state="disabled")

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

        to_error = False
        an_error = False

        for i, c in enumerate(self.cfg.cams):
            ru = False
            rd = False
            try:
                bgr = self._cam_snap(i)
                shot_dir = self.cfg.plc_shot_dir or tempfile.gettempdir()
                os.makedirs(shot_dir, exist_ok=True)
                shot_path = os.path.join(shot_dir, f"PLCshot_cam{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png")
                import cv2
                ok, buf = cv2.imencode('.png', bgr)
                if ok:
                    buf.tofile(shot_path)

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
            except Exception as e:
                an_error = True
                self._post_status(f"Cam{i+1} 解析エラー: {e}")

            try:
                with self._plc_lock:
                    self.plc.write_bit(c.dev_ru, ru)
                    self.plc.write_bit(c.dev_rd, rd)
            except Exception as e:
                to_error = True
                self._post_status(f"Cam{i+1} PLC書込エラー: {e}")

        with self._plc_lock:
            if to_error:
                self.plc.write_bit(self.cfg.dev_err_to, True)
            if an_error:
                self.plc.write_bit(self.cfg.dev_err_an, True)
            self.plc.pulse_bit(self.cfg.dev_done, self.cfg.done_ms)
            self.plc.write_bit(self.cfg.dev_busy, False)

        self._post_status(f"4カメラ返答完了 TO_ERR={int(to_error)} AN_ERR={int(an_error)}")

    def destroy(self):
        try:
            self.on_watch_stop()
            self.on_plc_disconnect()
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
