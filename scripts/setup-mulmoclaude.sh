#!/usr/bin/env bash
# MulmoClaude 前提チェック & 起動スクリプト (macOS / Linux)
# 使い方: ./scripts/setup-mulmoclaude.sh [--no-launch]
set -u

NO_LAUNCH=0
[ "${1:-}" = "--no-launch" ] && NO_LAUNCH=1

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m⚠\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✖\033[0m %s\n' "$1"; FAILED=1; }
FAILED=0

echo "== MulmoClaude 前提チェック =="

# Node.js >= 20.12
if command -v node >/dev/null 2>&1; then
  NODE_VER=$(node -v | sed 's/^v//')
  NODE_MAJOR=${NODE_VER%%.*}
  NODE_MINOR=$(echo "$NODE_VER" | cut -d. -f2)
  if [ "$NODE_MAJOR" -gt 20 ] || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -ge 12 ]; }; then
    ok "Node.js v$NODE_VER (要件: 20.12+)"
  else
    fail "Node.js v$NODE_VER は古すぎます。20.12 以上に更新してください (https://nodejs.org)"
  fi
else
  fail "Node.js が見つかりません。https://nodejs.org からインストールしてください"
fi

# Claude Code CLI
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code CLI $(claude --version 2>/dev/null | head -1)"
  warn "未認証の場合は一度 'claude' を実行して OAuth ログインを済ませてください"
else
  fail "Claude Code CLI が見つかりません。'npm install -g @anthropic-ai/claude-code' 後に 'claude' で認証してください"
fi

# ffmpeg (任意)
if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg あり（動画生成が使えます）"
else
  warn "ffmpeg なし — 動画生成を使うならインストール (macOS: brew install ffmpeg / Linux: apt install ffmpeg)"
fi

# Docker (任意・推奨)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  ok "Docker 稼働中（サンドボックスモードが自動で有効になります）"
else
  warn "Docker Desktop なし/停止中 — サンドボックスなしで動作します（個人利用なら可）。推奨: https://www.docker.com/products/docker-desktop/"
fi

# Gemini API キー (任意)
if [ -n "${GEMINI_API_KEY:-}" ]; then
  ok "GEMINI_API_KEY 設定済み（画像生成が使えます）"
else
  warn "GEMINI_API_KEY 未設定 — 画像生成ロールが無効になります。https://aistudio.google.com/apikey で取得可"
fi

echo
if [ "$FAILED" -ne 0 ]; then
  echo "必須要件が不足しています。上の ✖ を解消してから再実行してください。"
  exit 1
fi

if [ "$NO_LAUNCH" -eq 1 ]; then
  echo "チェック完了。起動するには: npx mulmoclaude@latest"
  exit 0
fi

echo "== MulmoClaude を起動します（Ctrl-C で停止 / 常駐させるなら tmux 内で実行）=="
exec npx mulmoclaude@latest
