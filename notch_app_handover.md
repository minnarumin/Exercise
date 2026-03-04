# notch_app 引き継ぎ説明書（開発者向け）

この文書は、`notch_app.py` を初めて触る開発者向けに、ロジック・主要関数・重要変数・運用時の注意点をまとめた引き継ぎ資料です。

---

## 1. プログラムの目的

`notch_app.py` は、Baslerカメラ画像からガラス基板のRU/RDノッチ有無を判定し、PLCへ結果返答する単一カメラ向けGUIアプリです。主な用途は以下です。

- 手動: 画像選択／単発撮像／連続Grabで解析確認
- 自動: PLCトリガ監視で撮像→解析→結果ビット書込→DONE返答
- 保守: 設定永続化、ログ/障害ダンプ、CSVローテーション

---

## 2. 全体アーキテクチャ

大きく次の層で構成されています。

1. **画像処理層**
   - `analyze_image(...)` が中核。
   - エッジ抽出→直線フィット→RU/RD領域差分面積で NOTCH 判定。

2. **デバイスI/O層**
   - `BaslerCamera`：Baslerカメラの接続/再接続/撮像。
   - `PLCClient`：PLC読み書き（Dワードのビット指定 `D100.3` もRMWで対応）。

3. **設定層**
   - `AppConfig`：JSON保存・復元（`~/.notch_app_config.json`）。

4. **UI/制御層**
   - `NotchApp`：Tk GUI、スレッド起動管理、PLC監視、HB、自動再接続、結果表示。

---

## 3. 起動～終了までのライフサイクル

### 起動時

`NotchApp.__init__` で以下を実行します。

- 設定ロード（`AppConfig.load()`）
- Tk変数初期化
- UI構築（メニュー・左ペイン・プレビュー・ログ欄）
- traceバインド（設定変更の自動保存）
- 一時ファイル清掃
- 自動再接続マネージャを `after(300, ...)` で開始

### 終了時

`destroy()` で以下を停止/解放します。

- PLC監視スレッド停止
- HBスレッド停止
- PLC切断／カメラクローズ
- 設定保存
- fault handler 停止

---

## 4. 画像処理ロジック（`analyze_image`）

`analyze_image(filepath, ...)` の処理概要:

1. 画像読込（Unicode対応）
2. 必要なら左右反転
3. 二値化→輪郭抽出→最大輪郭を基板本体とみなす
4. top/right/bottomのエッジ点群を取得
5. 各辺を `cv2.fitLine` で直線近似
6. 直線交点からRU/RDコーナー四角形ROIを生成
7. 理想矩形ROIと実輪郭マスク差分を面積化
8. `diff_thresh` 超過で `NOTCH` 判定
9. 重畳可視化画像（線・ROI・テキスト）を返却

返却dictには `img_bgr`、`ru_area`、`rd_area`、角度・傾き・各線端点などが含まれます。

---

## 5. 主要クラス/関数

## 5.1 `BaslerCamera`

役割: Baslerカメラ操作の薄いラッパ。

主なメソッド:

- `open()`：カメラオープン＋トリガ設定
- `_start_grabbing_if_needed()`：Grab開始保証
- `is_healthy()`：ヘルス判定
- `reopen()`：再接続
- `snap_bgr()`：1フレーム取得
- `close()`：停止/クローズ

ポイント:

- `use_sw_trigger` のON/OFFでソフトトリガ運用を切替
- 取得失敗時は `NotchApp._cam_snap_bgr()` 側で再試行

## 5.2 `PLCClient`

役割: MCプロトコルを使うPLC I/O。

主なメソッド:

- `connect()/close()`
- `read_bit()/write_bit()/pulse_bit()`
- `read_word()/write_word()`

ポイント:

- `D100.3` 形式のビット指定は内部で `read_word -> bit演算 -> write_word` のRMW処理。

## 5.3 `AppConfig`

役割: 設定の永続化。

- `load()`：JSON読み込み（未知キーは無視）
- `save()`：JSON保存（失敗時はloggerに例外記録）

保存対象:

- 解析パラメータ（trim, band, exclude, diffなど）
- PLC接続/デバイス
- HB設定
- 一時ファイル・CSV設定
- 自動再接続設定

## 5.4 `NotchApp`

役割: アプリ本体（GUI + 制御）。

代表的な処理群:

- **UIイベント**: `on_pick_files`, `on_preview`, `on_batch_process`, `on_capture_basler`
- **連続Grab**: `on_video_start/stop`, `_video_loop`
- **PLC監視**: `on_plc_watch_start/stop`, `_plc_loop`, `_plc_worker_loop`, `_handle_plc_trigger`
- **HB**: `_hb_start_if_needed`, `_hb_loop`
- **自動再接続**: `_auto_manager_loop`
- **CSV**: `_append_result_csv`（高速追記＋上限超過時ローテーション）

---

## 6. PLCトリガ処理の実際（重要）

`_handle_plc_trigger()` は以下の順で動作します。

1. BUSY=1、ERR_TO/ERR_AN=0 初期化
2. 撮像（失敗なら `to_error=True`）
3. 解析（失敗なら `an_error=True`）
4. CSV追記（成功/失敗とも記録）
5. RU/RD/ERRビット書込
6. DONEパルス
7. BUSY=0

補足:

- タイムアウト/解析失敗でもDONEは「処理完了通知」として発行される設計
- 結果ビット書込とDONEは同時ではなく、結果書込が先

---

## 7. 主要変数（運用で重要）

### 解析関連

- `trim_ratio_x`, `trim_ratio_y`
- `band_top/right/bottom`
- `corner_exclude_x_px`, `corner_exclude_y_px`
- `diff_thresh`
- `flip_horizontal`

### PLCデバイス関連

- `var_dev_trig`: トリガ入力
- `var_dev_ru`, `var_dev_rd`: 判定結果出力
- `var_dev_done`: 完了パルス
- `var_dev_busy`: 処理中フラグ
- `var_dev_err_to`, `var_dev_err_an`: エラー出力

### HB関連

- `var_dev_alive`, `var_alive_ms`, `var_alive_step`, `var_alive_auto`
- HB値は 10000超過時に0へ戻す

### 自動再接続関連

- `var_auto_reconnect`
- `var_auto_watch_on_ready`
- `manual_stopped`, `manual_disconnected`
- `_auto_state`（UI表示用状態文字列）

### スレッド/同期関連

- `self._plc_lock`: PLCアクセス直列化
- `self._cam_lock`: カメラアクセス直列化
- `self._csv_lock`: CSV書込保護
- `trigger_queue`: トリガFIFO

---

## 8. エラー時の挙動

- 解析失敗時:
  - ステータスにエラー表示
  - プレビューはRAW表示へフォールバック
  - CSVへ `ERROR_ANALYZE` 記録

- 撮像失敗時:
  - ステータスに撮像エラー表示
  - CSVへ `ERROR_CAPTURE` / `ERROR_TIMEOUT`

- PLC通信断:
  - 監視停止、接続クローズ、`plc_connected=False`
  - 自動再接続マネージャが復旧試行

---

## 9. 引き継ぎ時の確認チェックリスト

1. **依存**: `pypylon`, `pymcprotocol`, `opencv-python`, `numpy`, `Pillow`, `ttkbootstrap`
2. **設定**: `~/.notch_app_config.json` のバックアップ/復元
3. **PLCデバイス割当**: Trig/RU/RD/DONE/BUSY/ERR/HB
4. **保存先**: 出力フォルダ、PLC保存先の書込権限
5. **ログ確認**: `~/notch_app.log`, `~/notch_app_fault.log`
6. **CSV上限**: `csv_max_records` の運用値
7. **HB**: alive_ms, step, 上限超過リセット挙動

---

## 10. 変更時の推奨方針

- `notch_app.py` を更新したら `notch_app_commented.py` を同期
- PLCトリガ系は順序依存があるため、`_handle_plc_trigger` は小さく段階分割して変更
- 新規設定を追加したら:
  - `AppConfig` へ追加
  - Tk変数初期化
  - `_sync_cfg_from_vars`
  - 設定ダイアログUI
  - traceバインド

---

## 11. 最低限の動作確認コマンド

```bash
python -m py_compile notch_app.py notch_app_commented.py notch_app_win7.py
```

必要なら次版で、この引き継ぎ書に「関数ごとの入出力表（I/O契約）」を追加できます。
