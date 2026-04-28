# ============================================================
# IPTV 全流程启动脚本
# 逻辑：代理拉源 → 直连测活（过滤大陆不可直通的）→ 生成m3u → 同步 GitHub/Gist
#
# 使用方式：
#   右键 → "使用 PowerShell 运行"
#   或终端：powershell -File run_iptv.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$BASE = "C:\tools\IPTV"

# FFmpeg 路径
$env:PATH = "C:\tools\ffmpeg\bin;$env:PATH"

# 代理（仅拉取订阅源用，测活直连不过代理）
# 因为目标用户是大陆直连用户，测活直连才能过滤出真正可用的源
$PROXY = "http://127.0.0.1:3067"
$env:HTTP_PROXY  = $PROXY
$env:HTTPS_PROXY = $PROXY

Set-Location $BASE

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  IPTV-Apex-dzh 全流程" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# ---- 第1步：IPTV 主检测 ----
# --no-local       : 跳过 paste.txt（只用网络源）
# -w 120           : 境内并发120线程
# -t 8             : 境内超时8秒，境外自动×2
# --no-speed-check : 默认关速度检测（省时间）
# 代理：仅在 WebSourceFetcher 拉订阅源时生效，频道测活直连
Write-Host "[1/4] 拉源 + 直连测活（过滤大陆不可直通的源）..." -ForegroundColor Yellow
python IPTV-Apex-dzh.py `
    -w 120 `
    -t 8 `
    --no-local `
    --no-speed-check

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] IPTV 检测失败，退出码: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

if (-not (Test-Path "live_ok.txt")) {
    Write-Host "[ERROR] live_ok.txt 未生成！" -ForegroundColor Red
    exit 1
}

# ---- 第2步：生成 M3U ----
Write-Host "[2/4] 生成 live_ok.m3u ..." -ForegroundColor Yellow
python scripts\generate_m3u.py

# ---- 第3步：同步 Gist ----
Write-Host "[3/4] 同步 live_ok.txt → Gist ..." -ForegroundColor Yellow
python scripts\sync_to_gist.py

# ---- 第4步：GitHub 提交 ----
Write-Host "[4/4] GitHub 提交 ..." -ForegroundColor Yellow
git add -A
$status = git status --short
if ($status) {
    git commit -m "auto: $(Get-Date -Format 'yyyy-MM-dd HH:mm') UTC+8`n$(git diff --stat)"
    git push
    Write-Host "[OK] GitHub 提交成功" -ForegroundColor Green
} else {
    Write-Host "[SKIP] 无变更" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  完成！" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# 统计摘要
if (Test-Path ".iptv_stats.json") {
    $stats = Get-Content ".iptv_stats.json" -Raw | ConvertFrom-Json
    $valid   = $stats.valid   ?? 0
    $total   = $stats.total   ?? 0
    $written = $stats.written  ?? 0
    $rate    = if ($total -gt 0) { "{0:N1}%" -f ($valid / $total * 100) } else { "N/A" }
    Write-Host "  统计：待测 $total / 有效 $valid / 写入 $written / 有效率 $rate" -ForegroundColor White
}
