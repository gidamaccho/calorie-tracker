# MulmoClaude セットアップガイド（Claude Code 最適化版）

中島聡さんらが開発する [MulmoClaude](https://github.com/receptron/mulmoclaude)（Multi-modal Claude Code Client）を、
手元の Claude Code 環境で動かすためのガイドです。2026-07 時点の最新版 **v0.9.5** を対象にしています。

MulmoClaude は **ローカルマシン上で動く AI ネイティブアプリのプラットフォーム**です。
Claude Code をエンジン（ユニバーサルコントローラー）として使い、チャットで指示すると
マークダウン文書・チャート・フォーム・スプレッドシート・Wiki・画像などの GUI を Claude が呼び出して応答します。
買い物リストや映画ログのような「コレクション」、会計ソフト、定期実行タスクなどもチャットだけで作れます。

> **重要**: MulmoClaude はブラウザで `http://localhost:3001` を開いて使うローカルアプリです。
> claude.ai/code のリモートセッションではなく、**自分の PC（Mac / Windows / Linux）のターミナル**で実行してください。

---

## 1. 前提条件

| 必要なもの | 確認コマンド | 備考 |
| --- | --- | --- |
| Node.js **20.12 以上** | `node -v` | 22 系推奨 |
| Claude Code CLI（認証済み） | `claude --version` | 未認証なら一度 `claude` を起動して OAuth ログイン |
| ffmpeg（任意） | `ffmpeg -version` | 動画生成を使う場合のみ |
| Docker Desktop（任意・推奨） | `docker info` | サンドボックス実行用（後述） |

ffmpeg のインストール:

- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`
- Linux: `sudo apt install ffmpeg`

## 2. クイックスタート（最短ルート）

```bash
npx mulmoclaude@latest
```

これだけです。ランチャーがサーバーを起動し、ブラウザで http://localhost:3001 が開きます。

- UI 言語はブラウザ / OS の言語から自動判定されます（日本語環境なら日本語 UI）
- データはすべて `~/mulmoclaude/` 配下にプレーンなファイルとして保存されます
- **ターミナルを閉じるとサーバーも止まります**。常駐させたい場合は
  macOS/Linux なら `tmux` / `screen` 内で起動、Windows ならタスクスケジューラに登録してください

このリポジトリには前提チェック付きの起動スクリプトを同梱しています:

```bash
# macOS / Linux
./scripts/setup-mulmoclaude.sh

# Windows (PowerShell)
.\scripts\setup-mulmoclaude.ps1
```

## 3. 画像生成を有効にする（Gemini API キー）

画像生成・画像編集（`generateImage` / `editImage`、旅行ガイドやレシピの挿絵など）には
Google の Gemini API キーが必要です。無いと Artist などの画像系ロールが UI 上で無効になります。

1. [Google AI Studio](https://aistudio.google.com/apikey) で **Create API key**（個人利用なら無料枠で十分）
2. 環境変数として渡して起動:

```bash
# macOS / Linux
GEMINI_API_KEY=xxxxx npx mulmoclaude@latest

# Windows PowerShell（VAR=value 形式は使えないので $env: を使う）
$env:GEMINI_API_KEY = "xxxxx"
npx mulmoclaude@latest
```

環境変数はシェルの設定ファイル（`~/.zshrc` など）に `export GEMINI_API_KEY=...` として
書いておくと毎回の指定が不要になります。実行ディレクトリの `.env` ファイル（dotenv）でも読み込まれます。

## 4. セキュリティ: Docker サンドボックス（推奨）

MulmoClaude のバックエンドは Claude Code なので、**Bash を含むツールでマシン上のファイルを読み書きできます**。

- **Docker Desktop がインストールされていれば自動でサンドボックスモードになります**（設定不要）。
  コンテナにはワークスペース（`~/mulmoclaude/`）と Claude の設定（`~/.claude`）だけがマウントされ、
  それ以外のファイル（SSH 鍵や認証情報など）は Claude から見えません
- Docker が無い場合は警告バナーが出ますが、サンドボックスなしで動作します（個人のローカル利用なら許容範囲）
- サンドボックス内で git / gh を使いたい場合のみ、opt-in で認証情報を渡せます:
  - `SANDBOX_SSH_AGENT_FORWARD=1` — ホストの SSH エージェントを転送（秘密鍵はホストに残る）
  - `SANDBOX_MOUNT_CONFIGS=gh,gitconfig` — `~/.config/gh` と `~/.gitconfig` を読み取り専用でマウント
- デバッグ等でサンドボックスを切りたいとき: `npx mulmoclaude --disable-sandbox`
  （PowerShell でも使える CLI フラグ形式）

## 5. Claude Code との連携ポイント（最適化のキモ）

### 手持ちのスキルがそのまま使える

`~/.claude/skills/<name>/SKILL.md` に置いてある **Claude Code のユーザースキルを MulmoClaude から一覧・実行できます**。
General / Office / Tutor ロールで「スキルを見せて」と言うと Skills ビューが開き、**Run** ボタン一発で `/<skill-name>` が実行されます。

- プロジェクトスコープのスキルは `~/mulmoclaude/.claude/skills/` に置きます（名前が衝突したらこちらが優先）
- **注意（Docker サンドボックス時）**: `~/.claude/skills` がシンボリックリンクで `~/.claude` の外を指していると、
  コンテナ内ではリンク切れになりユーザースキルが見えません。実体を `~/.claude/skills/` に置くか、
  `--disable-sandbox` で回避してください

### 追加ツール・MCP サーバー

- `~/mulmoclaude/config/settings.json` と `mcp.json` で Claude Code 側の設定を追加できます
- MCP サーバーは Web UI の **Settings タブ**からも追加可能です

### ロールの使い分け

ロールを切り替えると Claude のコンテキストがリセットされ、そのロールに必要なツールだけが読み込まれるため
応答が速く・正確になります。用途別に General（万能）/ Office（文書・表計算）/ Guide & Planner（旅行・レシピ）/
Artist（画像）/ Tutor（学習）/ Storyteller（物語）があります。

## 6. スマホ・メッセージングアプリから使う（任意）

ブリッジプロセス経由で LINE / Telegram / Slack / Discord など多数のアプリから MulmoClaude に話しかけられます:

```bash
npx @mulmobridge/line@latest       # LINE
npx @mulmobridge/telegram@latest   # Telegram（TELEGRAM_BOT_TOKEN が必要）
npx @mulmobridge/slack@latest      # Slack
```

**ハマりどころ**: サーバーは起動のたびに認証トークンを再生成するため、サーバーだけ再起動すると
ブリッジ側が古いトークンのまま **401 エラーで沈黙**します。長時間ブリッジを動かすなら、
サーバーとブリッジの両方に同じ `MULMOCLAUDE_AUTH_TOKEN`（32 文字以上のランダム文字列推奨）を設定してください。

## 7. トラブルシューティング

| 症状 | 対処 |
| --- | --- |
| `claude` コマンドが見つからない | Claude Code CLI をインストールし、一度 `claude` を実行して OAuth 認証を完了する |
| Node のバージョンエラー | Node.js 20.12 以上に更新（`node -v` で確認） |
| Windows で `VAR=value コマンド` が効かない | PowerShell では `$env:VAR = "value"` を使うか、`--disable-sandbox` などの CLI フラグ形式を使う |
| Docker サンドボックスでユーザースキルが出ない | `~/.claude/skills` のシンボリックリンクを実体化する（上記 5 参照） |
| ブリッジが突然応答しなくなった（401） | `MULMOCLAUDE_AUTH_TOKEN` をサーバー・ブリッジ両方に固定設定する |
| 動画生成が失敗する | ffmpeg をインストールする |
| ログを見たい | `~/mulmoclaude/` 実行時のコンソール出力、またはサーバーの `server/system/logs/` 配下の日次 JSON ログ |

## 8. 開発者としていじりたい場合

```bash
git clone https://github.com/receptron/mulmoclaude.git
cd mulmoclaude && yarn install
cp .env.example .env    # GEMINI_API_KEY や VITE_LOCALE=ja をここに書く
yarn dev                # http://localhost:5173
```

ソース実行時のみ、UI 言語を `.env` の `VITE_LOCALE=ja` で明示固定できます（ビルド時に焼き込まれるため要再起動）。
アーキテクチャの詳細は [docs/developer.md](https://github.com/receptron/mulmoclaude/blob/main/docs/developer.md) を参照してください。

## 参考リンク

- 本体リポジトリ: https://github.com/receptron/mulmoclaude
- npm パッケージ: https://www.npmjs.com/package/mulmoclaude
- 設計思想（MANIFEST）: https://github.com/receptron/mulmoclaude/blob/main/MANIFEST.md
- 中島聡さんによるデモ解説: https://zenn.dev/singularity/articles/2026-06-14-bootcamp-4th-nakajima-mulmoclaude
- リモートアクセス機能の解説: https://zenn.dev/singularity/articles/2026-07-03-mulmoclaude-remote-access
