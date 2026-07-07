# MulmoClaude 前提チェック & 起動スクリプト (Windows PowerShell)
# 使い方: .\scripts\setup-mulmoclaude.ps1 [-NoLaunch]
param([switch]$NoLaunch)

$failed = $false
function OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  [X] $msg" -ForegroundColor Red; $script:failed = $true }

Write-Host "== MulmoClaude 前提チェック =="

# Node.js >= 20.12
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $ver = (node -v).TrimStart("v")
    if ([version]$ver -ge [version]"20.12.0") {
        OK "Node.js v$ver (要件: 20.12+)"
    } else {
        Fail "Node.js v$ver は古すぎます。20.12 以上に更新してください (https://nodejs.org)"
    }
} else {
    Fail "Node.js が見つかりません。https://nodejs.org からインストールしてください"
}

# Claude Code CLI
if (Get-Command claude -ErrorAction SilentlyContinue) {
    OK "Claude Code CLI $(claude --version 2>$null | Select-Object -First 1)"
    Warn "未認証の場合は一度 'claude' を実行して OAuth ログインを済ませてください"
} else {
    Fail "Claude Code CLI が見つかりません。'npm install -g @anthropic-ai/claude-code' 後に 'claude' で認証してください"
}

# ffmpeg (任意)
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    OK "ffmpeg あり（動画生成が使えます）"
} else {
    Warn "ffmpeg なし — 動画生成を使うなら: winget install Gyan.FFmpeg"
}

# Docker (任意・推奨)
$dockerOk = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
}
if ($dockerOk) {
    OK "Docker 稼働中（サンドボックスモードが自動で有効になります）"
} else {
    Warn "Docker Desktop なし/停止中 — サンドボックスなしで動作します。推奨: https://www.docker.com/products/docker-desktop/"
}

# Gemini API キー (任意)
if ($env:GEMINI_API_KEY) {
    OK "GEMINI_API_KEY 設定済み（画像生成が使えます）"
} else {
    Warn 'GEMINI_API_KEY 未設定 — 画像生成が無効になります。設定例: $env:GEMINI_API_KEY = "xxxxx"'
}

Write-Host ""
if ($failed) {
    Write-Host "必須要件が不足しています。上の [X] を解消してから再実行してください。"
    exit 1
}

if ($NoLaunch) {
    Write-Host "チェック完了。起動するには: npx mulmoclaude@latest"
    exit 0
}

Write-Host "== MulmoClaude を起動します（Ctrl-C で停止）=="
npx mulmoclaude@latest
