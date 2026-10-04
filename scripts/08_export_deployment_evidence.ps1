param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8080,
  [string]$Token = "",
  [string]$Out = "deployment_evidence.md"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Token) {
  $TokenPath = Join-Path $Root "web\config\server.token"
  $TempTokenPath = Join-Path $env:TEMP "websplatserve_server.token"
  if (Test-Path -LiteralPath $TokenPath) {
    $Token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
  } elseif (Test-Path -LiteralPath $TempTokenPath) {
    $Token = (Get-Content -LiteralPath $TempTokenPath -Raw).Trim()
  } else {
    throw "Token was not provided and web\config\server.token does not exist. Run scripts/02_start_server.ps1 first."
  }
}

$Headers = @{ "X-Auth-Token" = $Token }
$Uri = "http://$HostName`:$Port/api/telemetry/evidence.md"
Write-Host "[08] Exporting deployment evidence from $Uri"
$Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers $Headers
Set-Content -LiteralPath $Out -Value $Response.Content -Encoding UTF8
Write-Host "[08] Wrote $Out"
