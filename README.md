# calorie-tracker

## 📖 Kindle 行間メモ (`/kindle-notes/`)

iPad で Kindle を読みながら、ページの行間に Apple Pencil で書き込むための Web アプリです。
`public/kindle-notes/` に単体の HTML アプリとして入っており、デプロイ後は
`https://<user>.github.io/calorie-tracker/kindle-notes/` で開けます。

### 使い方

1. Kindle アプリで書き込みたいページを開く
2. Apple Pencil で画面左下の角から内側へスワイプしてスクリーンショットを撮り、写真に保存
3. このアプリを開き「＋ スクリーンショットを取り込む」から写真を選ぶ(複数可)
4. ページを開き、ピンチで拡大して行間に Apple Pencil で書き込む(指は移動・拡大縮小)

### 書き込みが「勝手に消えない」ための仕組み

- 1 画書くごとに端末内の IndexedDB へ即時自動保存(保存ボタン不要)
- `navigator.storage.persist()` で永続ストレージを要求し、ブラウザによる自動削除を抑止
- 消えるのは自分で「消しゴム」「元に戻す」「ページ削除(確認ダイアログあり)」を使ったときだけ
- Safari の長期未使用データ削除に備えて「ホーム画面に追加」を案内(ホーム画面アプリは削除対象外)
- 万一に備えた「バックアップ書き出し / 読み込み」(画像+書き込みを JSON ファイルに保存・復元)

※ iPadOS の仕様上、Kindle アプリの画面そのものにオーバーレイして直接書き込むことは
サードパーティアプリにはできないため、スクリーンショットに書き込む方式を採用しています。

その他の機能: ペン(筆圧対応)/ 蛍光マーカー / ストローク単位の消しゴム / 取り消し・やり直し /
ピンチズーム・パン / パームリジェクション / ページ間の前後移動 / PNG 書き出し(共有シート対応) /
オフライン起動(Service Worker)

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
