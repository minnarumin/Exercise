# ガラス基板ノッチ判定ツール 仕様書

## 1. 概要
本ソフトは、Basler GigEカメラで取得した画像を解析し、ガラス基板のノッチ有無（RU/RD）を判定するデスクトップアプリケーションである。  
加えて PLC 連携（トリガ監視・判定返答・ハートビート・自動再接続）、結果画像保存、CSV ログ保存、長時間運用向けの障害調査ログ出力を行う。

- 実行ファイル: `notch_app.py`
- 説明付き同期版: `notch_app_commented.py`
- 設定ファイル: `~/.notch_app_config.json`
- アプリログ: `~/.notch_app.log`
- フォルト/フリーズ調査ログ: `~/.notch_app_fault.log`

---

## 2. 主要機能

### 2.1 画像解析
- 直線近似ベースで上辺・側辺・下辺を推定。
- コーナーROI（RU/RD）の差分面積から `NOTCH` / `NO NOTCH` を判定。
- 解析可視化画像（線、ROI、判定文字、必要時 FLIP 表示）を生成。
- 解析結果として以下を保持:
  - `ru_area`, `rd_area`, `ru_result`, `rd_result`
  - 角度/傾き（top/side/bottom）
  - 近似線端点（top/side/bottom）

### 2.2 画像入力
- ファイル選択（複数）による手動プレビュー・一括処理。
- Basler 単発撮像。
- 連続Grab（ライブ表示）開始/停止。

### 2.3 PLC連携
- PLC トリガ監視（立ち上がり検知）。
- キュー化したトリガをワーカースレッドで順次処理。
- 撮像→解析→PLC返答（RU/RD/エラーフラグ/DONEパルス）。
- ハートビート（Dデバイスの周期加算書込み）。
- 自動再接続・自動監視開始（設定で ON/OFF）。

### 2.4 保存・ログ
- PLC撮像画像保存（`PLCshot_*.png`）。
- 解析結果画像保存（`*_result.png`）。
- `result.csv` 追記（最大件数ローテーション）。
- 一時ファイル上限を超えた場合の自動削除。
- 実行ログ/未捕捉例外/フォルトダンプの記録。

---

## 3. UI仕様

### 3.1 メイン構成
- 左ペイン: ファイル選択、解析パラメータ、撮像/PLC操作。
- 右ペイン: 画像プレビュー（ズーム/パン）と情報欄。
- 下部情報欄:
  - ステータス（最新5件、ワードラップ表示）
  - 解析結果（最新5件）

### 3.2 設定ダイアログ
- PLC連携設定
  - 接続先（IP/Port）
  - Read/Write デバイス割当
  - 撮像条件（SWトリガ、Timeout、DONE幅）
  - 自動復旧（自動再接続、自動監視開始）
- カメラ設定
  - 検出済みGigEカメラ選択
- 生存カウンタ設定
  - Dデバイス、周期、増分、自動開始
- 一時ファイル管理
  - 保持上限、対象プレフィックス（カンマ区切り）
- 結果CSV/保存先設定
  - CSV最大件数、PLC撮像保存先

---

## 4. 設定ファイル仕様（`AppConfig`）

### 4.1 解析
- `trim_ratio_x`, `trim_ratio_y`, `diff_thresh`
- `band_top`, `band_right`, `band_bottom`
- `corner_exclude_x_px`, `corner_exclude_y_px`
- `auto_preview`, `flip_horizontal`

### 4.2 出力
- `output_dir`

### 4.3 カメラ/PLC
- `camera_index`
- `plc_ip`, `plc_port`
- `dev_trig`, `dev_ru`, `dev_rd`, `dev_done`, `dev_busy`, `dev_err_to`, `dev_err_an`
- `use_sw_trig`, `timeout_ms`, `done_ms`

### 4.4 ハートビート
- `dev_alive`, `alive_ms`, `alive_step`, `alive_auto`

### 4.5 ファイル管理
- `temp_max_files`, `temp_prefixes`
- `csv_max_records`, `plc_shot_dir`

### 4.6 自動復旧
- `auto_reconnect`, `auto_watch_on_ready`

---

## 5. PLCデバイス指定仕様

### 5.1 通常デバイス
- `M100`, `X10`, `Y20` などのビットデバイスを Read/Write 対象に利用可能。

### 5.2 Dワードのビット指定
- `D100.3` 形式（`D*.n`）を Read/Write 対応。
- `n` は `0..15`。
- 実装方式は Read-Modify-Write（ワード読取→ビット演算→ワード書戻し）。

---

## 6. 動作フロー

### 6.1 手動プレビュー
1. ファイル選択。
2. パラメータ入力（変更時は200msデバウンスで自動プレビュー可）。
3. `analyze_image()` 実行。
4. 結果画像と解析結果欄を更新。
5. 解析失敗時は生画像（RAW）をプレビュー表示。

### 6.2 PLCトリガ処理
1. 監視スレッドがトリガ立ち上がり検知。
2. トリガ情報をキューへ投入。
3. ワーカースレッドが撮像→解析→CSV保存→PLC返答を実行。
4. 失敗時はエラー行をCSV記録、必要に応じてRAW表示。

---

## 7. 長時間運用・障害耐性
- カメラ排他ロック・PLC排他ロックで同時アクセスを抑制。
- トリガキューで処理を直列化。
- 取得失敗時の再試行と再オープン。
- カメラアイドル時間超過時の再オープン。
- PLC読取エラー連続時の監視再起動誘導。
- ローテーションログとフォルトダンプで事後調査可能。

---

## 8. 既知の注意点
- DビットRMWは同一ワードに外部書込みがあると競合しうるため、PLC側で運用設計（専用ワード化など）が望ましい。
- トリガキュー満杯時は最新トリガ破棄となるため、必要に応じてキューサイズやPLC側信号設計を調整する。

---

## 9. 起動方法
```bash
python notch_app.py
```

## 10. 構文チェック
```bash
python -m py_compile notch_app.py notch_app_commented.py
```
