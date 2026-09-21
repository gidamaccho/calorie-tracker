# 🥗 カロリー管理

食事とカロリーを記録する React + TypeScript + Vite のアプリ。データは端末の localStorage に保存されます。

## Jev による食事の自動分類

追加した食事を [TypeSafe AI](https://typesafe.ai) の System One モデル **Jev** に判定させ、
主食 / 主菜 / 副菜 / 汁物 / 間食 / 飲み物 / その他 の7区分に自動でタグ付けします。
Jev は文章を生成せず、選択肢とその確率だけを返す判定特化モデルなので、この用途では LLM より高速・安価です。

### 設定

このアプリはバックエンドを持たない静的サイトなので、APIキーはビルド成果物に含めず、
**利用者が自分のキーを入力する方式（BYOK）** にしています。

1. TypeSafe AI で APIキーを取得する
2. アプリ下部の「⚡ Jev 自動分類」→「設定」を開く
3. キーを貼り付けて「保存」

キーはその端末の `localStorage`（`jev-api-key`）にのみ保存され、判定時に `api.typesafe.ai` へ直接送られます。
リポジトリにも `dist/` にもキーは含まれません。

### 挙動

- キー未設定なら Jev は呼ばれず、アプリは従来どおり動きます
- 判定に失敗しても食事の記録は必ず残り、画面上部に警告だけが出ます
- 確信度が 50% 未満の判定は採用せず、未分類のままにします
- タイムアウトは 10 秒

### 実装

| ファイル | 役割 |
| --- | --- |
| `src/lib/jev.ts` | `POST /v1/systemone` を叩く最小クライアント（型付き answers のパースとエラー分類） |
| `src/lib/mealCategory.ts` | 7区分の定義と `classifyMeal()` |
| `src/hooks/useJevKey.ts` | APIキーの保持（BYOK） |
| `src/hooks/useMealClassifier.ts` | 追加された食事を非同期で判定 |
| `src/components/JevSettings.tsx` | キー入力UI |

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
