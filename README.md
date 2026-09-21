# 🥗 カロリー管理

食事とカロリーを記録する React + TypeScript + Vite のアプリ。データは端末の localStorage に保存されます。

## 写真から記録する

食事の写真を撮るだけで、料理名と推定カロリーがフォームに入り、区分のタグが付きます。
2つのモデルを役割で分けています。

```
📷 写真 ──▶ Claude（claude-opus-5）──▶ 「鮭の塩焼き定食 / 620 kcal」──▶ Jev ──▶ 🍚 主食
             画像を読む・量を見積もる          フォームに自動入力          区分を判定
```

**なぜ2段構えなのか**: [Jev](https://typesafe.ai) は文章を生成せず、選択肢とその確率だけを返す判定特化モデルで、
`state` に取れるのは文字列・JSON・配列だけです。画像は受け取れないため、写真を読む工程は Claude が担当し、
その結果を Jev が判定します。判定は Jev のほうが高速・安価です。

### 設定

このアプリはバックエンドを持たない静的サイトなので、APIキーはビルド成果物に含めず、
**利用者が自分のキーを入力する方式（BYOK）** にしています。

1. 画面下部の「⚡ AI 設定」を開く
2. Claude のキー（写真の読み取り）と Jev のキー（自動分類）を入れて保存

キーはその端末の `localStorage` にのみ保存され、それぞれ `api.anthropic.com` / `api.typesafe.ai` へ直接送られます。
リポジトリにも `dist/` にもキーは含まれません。

### 挙動

- **キーは片方だけでも動きます**。Claude のキーがなければ写真ボタンは出ず、Jev のキーがなければタグが付かないだけです
- 写真は送信前にブラウザ側で長辺1024pxのJPEGに縮小します（原寸のスマホ写真は遅く高くつくため）
- 読み取り結果はフォームに入るだけなので、追加前に手で直せます
- 解析や判定に失敗しても記録は妨げられず、警告が出るだけです
- 食べ物が写っていない写真は、誤った推定をせず手入力を促します
- 確信度50%未満の区分判定は採用せず、未分類のままにします
- Anthropic SDK は本体より大きいので動的 import で分離し、写真を使うときだけ読み込みます

### 実装

| ファイル | 役割 |
| --- | --- |
| `src/lib/vision.ts` | Claude で写真から料理名・カロリーを抽出（structured outputs でスキーマを保証） |
| `src/lib/image.ts` | 送信前の縮小・JPEG変換 |
| `src/lib/jev.ts` | `POST /v1/systemone` を叩く最小クライアント |
| `src/lib/mealCategory.ts` | 7区分の定義と `classifyMeal()` |
| `src/hooks/useApiKey.ts` | APIキーの保持（BYOK） |
| `src/hooks/useMealPhoto.ts` | 写真の縮小から読み取りまで |
| `src/hooks/useMealClassifier.ts` | 追加された食事を非同期で判定 |
| `src/components/AiSettings.tsx` | キー入力UI |

### 調整するとしたら

- `src/lib/vision.ts` の `output_config.effort` が精度と待ち時間のつまみです（現在 `medium`）
- `src/lib/image.ts` の `MAX_EDGE` を上げると細部が読めますが、その分トークンが増えます
- `src/lib/mealCategory.ts` の `MIN_CONFIDENCE` がタグを付ける確信度の下限です

## 開発

```sh
npm ci
npm run dev
npm run lint
npm run build
```

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
