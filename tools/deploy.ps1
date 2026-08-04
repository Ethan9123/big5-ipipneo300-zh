# Deploy dist/ to Cloudflare Pages.
#
#   .\tools\deploy.ps1            -> preview branch, safe to run
#   .\tools\deploy.ps1 -Production -> the live site (asks for confirmation)
#
# Credentials come from .env in the project root, which this script never prints.
# Account id is taken from the dashboard URL and is not a secret.

param([switch]$Production)

$ErrorActionPreference = 'Stop'
$Root    = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $Root '.env'
$Dist    = Join-Path $Root 'dist'
$Project = 'big5-ipipneo300-zh'
# Account id is the first path segment of your Pages dashboard URL:
#   https://dash.cloudflare.com/<ACCOUNT_ID>/pages/view/<project>
# Put CLOUDFLARE_ACCOUNT_ID=... in .env beside the token, or set it in the shell.
$Account = $env:CLOUDFLARE_ACCOUNT_ID

if (-not (Test-Path $EnvFile)) {
  Write-Host "缺少 $EnvFile" -ForegroundColor Red
  Write-Host "请在其中写入一行：CLOUDFLARE_API_TOKEN=你的token"
  exit 1
}
if (-not (Test-Path (Join-Path $Dist 'index.html'))) {
  Write-Host "缺少 dist/index.html —— 先跑 python tools\make_dist.py" -ForegroundColor Red
  exit 1
}

$env:WRANGLER_SEND_METRICS = 'false'
if (-not $Account) {
  $m = Select-String -Path $EnvFile -Pattern '^CLOUDFLARE_ACCOUNT_ID=(.+)$'
  if ($m) { $Account = $m.Matches[0].Groups[1].Value.Trim() }
}
if (-not $Account) {
  Write-Host '缺少 CLOUDFLARE_ACCOUNT_ID（放进 .env 或设为环境变量）' -ForegroundColor Red
  exit 1
}
$env:CLOUDFLARE_ACCOUNT_ID = $Account

# Re-run the corpus gate and the packaging pre-flight before anything leaves the machine.
Write-Host "`n=== 部署前复验 ===" -ForegroundColor Cyan
python (Join-Path $PSScriptRoot 'make_dist.py')
if ($LASTEXITCODE -ne 0) { Write-Host "验收未通过，已中止。" -ForegroundColor Red; exit 1 }

$branch = if ($Production) { 'main' } else { 'preview' }

if ($Production) {
  Write-Host "`n即将发布到生产环境 ($Project / $branch)。" -ForegroundColor Yellow
  Write-Host "这会替换 https://big5.try-board-game.uk/ 上的线上版本。"
  $ans = Read-Host "输入 yes 确认"
  if ($ans -ne 'yes') { Write-Host "已取消。"; exit 0 }
}

Write-Host "`n=== wrangler pages deploy ($branch) ===" -ForegroundColor Cyan
npx --yes wrangler@latest pages deploy $Dist `
  --project-name $Project `
  --branch $branch `
  --env-file $EnvFile `
  --commit-message "empirical percentile tables + 243 combination profiles + CSP"

if ($LASTEXITCODE -ne 0) { Write-Host "`n部署失败。" -ForegroundColor Red; exit 1 }
Write-Host "`n完成。" -ForegroundColor Green
if (-not $Production) {
  Write-Host "预览地址在上面的输出里。确认无误后跑：  .\tools\deploy.ps1 -Production"
}
