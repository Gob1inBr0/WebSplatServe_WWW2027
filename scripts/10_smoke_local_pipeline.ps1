param(
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe",
  [int]$Rows = 160
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[10] Running local smoke pipeline in TEMP"
$SmokeRoot = Join-Path $env:TEMP "websplatserve_smoke"
$PlyPath = Join-Path $SmokeRoot "scene.ply"
$OutDir = Join-Path $SmokeRoot "assets"
$TraceCsv = Join-Path $SmokeRoot "joint-trace.csv"
$BenchCsv = Join-Path $SmokeRoot "serving-benchmark.csv"

New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

$code = @"
from pathlib import Path
from web.tools.test_web_export import write_test_ply
write_test_ply(Path(r'$PlyPath'), $Rows)
print(r'$PlyPath')
"@
$code | & $Python -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& powershell -ExecutionPolicy Bypass -File scripts\04_export_scene.ps1 `
  -PlyPath $PlyPath `
  -SceneId smoke_temp `
  -OutDir $OutDir `
  -BackendProfile vanilla-3dgs-sh `
  -Python $Python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Manifest = Join-Path $OutDir "websplatserve_manifest.json"

& powershell -ExecutionPolicy Bypass -File scripts\05_run_scheduler_simulation.ps1 `
  -SceneId smoke_temp `
  -ManifestPath $Manifest `
  -OutCsv $TraceCsv `
  -Policy joint `
  -BandwidthMbps 10 `
  -RttMs 60 `
  -Python $Python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& powershell -ExecutionPolicy Bypass -File scripts\06_run_policy_benchmark.ps1 `
  -SceneId smoke_temp `
  -ManifestPath $Manifest `
  -OutCsv $BenchCsv `
  -Bandwidths "2,10" `
  -Rtts "30" `
  -Python $Python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[10] Smoke pipeline passed"
Write-Host "[10] PLY: $PlyPath"
Write-Host "[10] Assets: $OutDir"
Write-Host "[10] Trace CSV: $TraceCsv"
Write-Host "[10] Benchmark CSV: $BenchCsv"

