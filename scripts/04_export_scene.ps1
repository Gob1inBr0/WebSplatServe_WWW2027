param(
  [Parameter(Mandatory = $true)]
  [string]$PlyPath,
  [string]$SceneId = "scene_a",
  [string]$OutDir = "",
  [ValidateSet("vanilla-3dgs-sh", "compressed-decoded-sh", "compact-pruned-sh")]
  [string]$BackendProfile = "vanilla-3dgs-sh",
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path -LiteralPath $PlyPath)) {
  throw "PLY file not found: $PlyPath"
}

if (-not $OutDir) {
  $OutDir = "web\generated\websplatserve\$SceneId"
}
Write-Host "[04] Exporting $PlyPath"
Write-Host "[04] Output: $OutDir"
& $Python web\tools\export_websplatserve_assets.py $PlyPath $OutDir --backend-profile $BackendProfile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$DefaultOut = "web\generated\websplatserve\$SceneId"
if ($OutDir -eq $DefaultOut) {
  Write-Host "[04] Viewer manifest: /web/generated/websplatserve/$SceneId/manifest.json"
  Write-Host "[04] Enriched manifest: web/generated/websplatserve/$SceneId/websplatserve_manifest.json"
} else {
  Write-Host "[04] Viewer manifest file: $(Join-Path $OutDir 'manifest.json')"
  Write-Host "[04] Enriched manifest file: $(Join-Path $OutDir 'websplatserve_manifest.json')"
}
