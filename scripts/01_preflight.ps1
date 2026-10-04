param(
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[01] WebSplatServe preflight"
Write-Host "Root: $Root"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python not found: $Python"
}

& $Python --version

Write-Host "[01] Running focused tests"
& $Python web\tools\run_tests.py websplatserve telemetry web_export
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[01] Running syntax checks"
$Cache = Join-Path $env:TEMP "websplatserve_pycache"
& $Python -X "pycache_prefix=$Cache" -m py_compile `
  web\serving\manifest.py `
  web\serving\adaptive_scheduler.py `
  web\serving\backend_profiles.py `
  web\tools\export_websplatserve_assets.py `
  web\tools\run_serving_benchmark.py `
  web\tools\collect_deployment_evidence.py `
  web\tools\test_websplatserve_manifest.py `
  web\tools\test_websplatserve_scheduler.py `
  web\server\telemetry.py `
  web\server\api_server.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[01] Preflight passed"

