# Mitsubishi PLC Recipe Manager

TypeScript + React + [`mcprotocol`](https://github.com/raydotac/mcprotocol) を使って、三菱PLCの `ZR1 ~ ZR1000` に保存されたレシピを管理するアプリです。

## 構成

- `src/`: Reactフロントエンド
- `server/`: Express + mcprotocol APIサーバー

ブラウザから直接MCプロトコルのTCP通信はできないため、Node.jsサーバー経由でPLCに接続します。

## レシピ配置ルール

- 対象範囲: `ZR1 ~ ZR1000`
- UI上は `recipeNo: 1~100`
- `wordsPerRecipe` で1レシピあたりのワード数を指定
- 開始アドレス計算: `ZR((recipeNo - 1) * wordsPerRecipe + 1)`

例: `recipeNo=2`, `wordsPerRecipe=10` の場合 `ZR11~ZR20` を使用。

## 起動

```bash
npm install
npm run dev
```

- フロント: `http://localhost:5173`
- API: `http://localhost:3001`

必要に応じてフロント側 `.env` に `VITE_API_BASE_URL` を設定してください。

