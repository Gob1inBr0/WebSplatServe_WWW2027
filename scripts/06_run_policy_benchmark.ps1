param(
  [string]$SceneId = "scene_a",
  [string]$Policies = "full,naive,bandwidth,viewport,gpu,joint",
  [string]$Bandwidths = "2,5,10,30,100",
  [string]$Rtts = "30,120",
  [string]$ManifestPath = "",
  [string]$OutCsv = "",
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Manifest = if ($ManifestPath) { $ManifestPath } else { "web\generated\websplatserve\$SceneId\websplatserve_manifest.json" }
if (-not (Test-Path -LiteralPath $Manifest)) {
  throw "Manifest not found: $Manifest. Run scripts/04_export_scene.ps1 first."
}

if (-not $OutCsv) {
  $OutCsv = "web\generated\experiments\$SceneId-serving-benchmark.csv"
}
Write-Host "[06] Running policy/network benchmark"
& $Python web\tools\run_serving_benchmark.py $Manifest --policies $Policies --bandwidths $Bandwidths --rtts $Rtts --out $OutCsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[06] Benchmark CSV: $OutCsv"
