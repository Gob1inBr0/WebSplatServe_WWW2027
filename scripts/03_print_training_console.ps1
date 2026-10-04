param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8080
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[03] Remote training entrypoint"
Write-Host "Open: http://$HostName`:$Port/web/console/"
Write-Host ""
Write-Host "Use this step when you do not already have a standard SH PLY."
Write-Host "Training needs a remote GPU server, algorithm repo path, workspace root, output root, and adapter selection."
Write-Host "If you already have a standard SH PLY, skip to scripts/04_export_scene.ps1."

