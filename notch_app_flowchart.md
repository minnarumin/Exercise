# notch_app 動作フローチャート

この資料は `notch_app.py`（1カメラ版）の主な実行フローを Mermaid で可視化したものです。

## 1. 起動〜自動再接続〜監視開始

```mermaid
flowchart TD
    A[アプリ起動 NotchApp初期化] --> B[設定ロード/AppConfig.load]
    B --> C[UI構築]
    C --> D[traceバインド・一時ファイル清掃]
    D --> E[自動接続マネージャ開始]

    E --> F{auto_reconnect有効か?}
    F -- No --> E
    F -- Yes --> G{PLC接続済みか?}
    G -- No --> H[PLC接続試行]
    H --> I{接続成功?}
    I -- No --> E
    I -- Yes --> J[PLC接続済み状態へ]
    G -- Yes --> J

    J --> K{カメラ正常か?}
    K -- No --> L[カメラ再接続試行]
    L --> M{成功?}
    M -- No --> E
    M -- Yes --> N[監視待機]
    K -- Yes --> N

    N --> O{auto_watch_on_ready有効 かつ 手動停止でない?}
    O -- No --> E
    O -- Yes --> P[PLC監視開始 on_plc_watch_start]
    P --> E
```

## 2. PLCトリガ処理（1トリガあたり）

```mermaid
flowchart TD
    A[PLCポーリングループでTrig立上り検出] --> B[トリガをキュー投入]
    B --> C[ワーカースレッドがトリガ取得]
    C --> D[_handle_plc_trigger開始]

    D --> E[BUSY=1 ERR_TO=0 ERR_AN=0]
    E --> F[撮像して一時画像保存]
    F --> G{撮像成功?}

    G -- No --> H[TO_ERR=true ERROR_TIMEOUT/ERROR_CAPTUREをCSV追記]
    G -- Yes --> I[画像解析 analyze_image]
    I --> J{解析成功?}

    J -- No --> K[AN_ERR=true ERROR_ANALYZEをCSV追記]
    J -- Yes --> L[RU/RD判定 結果画像保存 CSV追記]

    H --> M[PLCへ結果/エラー書込]
    K --> M
    L --> M

    M --> N[完了パルス DONE]
    N --> O[BUSY=0]
    O --> P[ステータス/ログ更新]
```

## 3. 手動操作フロー（画像選択/撮像/プレビュー）

```mermaid
flowchart TD
    A[ユーザー操作] --> B{操作種別}

    B -- 画像選択 --> C[ファイルリスト更新]
    C --> D{auto_preview有効?}
    D -- Yes --> E[on_preview]
    D -- No --> Z[待機]

    B -- 単発撮像 --> F[Basler撮像]
    F --> G[Tempへ保存しリスト追加]
    G --> E

    B -- 連続Grab開始 --> H[video_thread開始]
    H --> I[_video_loopで撮像しキャンバス更新]
    I --> I

    E --> J[analyze_image実行]
    J --> K{解析成功?}
    K -- Yes --> L[_show_previewで結果重畳表示]
    K -- No --> M[_show_raw_previewで生画像表示]
    L --> Z
    M --> Z
```

## 4. ハートビート（HB）フロー

```mermaid
flowchart TD
    A[HB自動有効でPLC接続] --> B[_hb_start_if_needed]
    B --> C[初期値をPLCから読取]
    C --> D[_hb_loop開始]
    D --> E[hb_valueにalive_step加算]
    E --> F{10000超過?}
    F -- Yes --> G[hb_value=0にリセット]
    F -- No --> H[そのまま使用]
    G --> I[PLC Dデバイスへwrite_word]
    H --> I
    I --> J[alive_ms待機]
    J --> D
```

---

必要であれば次版として、`notch_app_4cam.py` の「カメラ別トリガ/個別DONE/個別ERR」の詳細フローも別セクションで追加できます。
