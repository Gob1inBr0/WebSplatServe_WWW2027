param(
  [string]$SceneId = "scene_a",
  [ValidateSet("naive", "bandwidth", "viewport", "gpu", "joint", "full")]
  [string]$Policy = "joint",
  [double]$BandwidthMbps = 10,
  [double]$RttMs = 60,
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
  $OutCsv = "web\generated\experiments\$SceneId-$Policy-trace.csv"
}
Write-Host "[05] Running scheduler simulation"
& $Python web\serving\adaptive_scheduler.py $Manifest --policy $Policy --bandwidth-mbps $BandwidthMbps --rtt-ms $RttMs --out-csv $OutCsv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[05] Trace CSV: $OutCsv"
