param(
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[09] Running all local checks"
& powershell -ExecutionPolicy Bypass -File scripts\01_preflight.ps1 -Python $Python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[09] Local checks passed"

