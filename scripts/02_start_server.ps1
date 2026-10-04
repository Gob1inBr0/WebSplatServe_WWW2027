param(
  [string]$Python = "C:\Users\ly\AppData\Local\Programs\Python\Python313\python.exe",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8080,
  [string]$Token = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[02] Starting WebSplatServe server"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python not found: $Python"
}

$TokenPath = Join-Path $Root "web\config\server.token"
$TempTokenPath = Join-Path $env:TEMP "websplatserve_server.token"

function Read-ExistingToken {
  if ($Token) { return $Token }
  if (Test-Path -LiteralPath $TokenPath) {
    return (Get-Content -LiteralPath $TokenPath -Raw).Trim()
  }
  if (Test-Path -LiteralPath $TempTokenPath) {
    return (Get-Content -LiteralPath $TempTokenPath -Raw).Trim()
  }
  return ""
}

function Test-PortListening {
  $line = netstat -ano | Select-String ":$Port\s+.*LISTENING" | Select-Object -First 1
  return [bool]$line
}

function Test-Health([string]$UseToken) {
  $Headers = @{ "X-Auth-Token" = $UseToken }
  return Invoke-WebRequest -UseBasicParsing -Uri "http://$HostName`:$Port/api/health" -Headers $Headers
}

$Listening = Test-PortListening
if ($Listening) {
  Write-Host "[02] Port $Port is already listening. Reusing existing server."
  $Token = Read-ExistingToken
  if (-not $Token) {
    throw "Port $Port is already in use, but no token was provided and no token file exists. Pass -Token for the running server."
  }
  try {
    $Health = Test-Health $Token
  } catch {
    throw "Port $Port is in use, but the available token was rejected. Pass -Token for the running server or stop the existing process."
  }
  Write-Host "[02] Health status: $($Health.StatusCode)"
  Write-Host "[02] Console: http://$HostName`:$Port/web/console/"
  Write-Host "[02] Token: $Token"
  exit 0
}

if (-not $Token) {
  $Token = Read-ExistingToken
}
if (-not $Token) {
  $Token = [Convert]::ToBase64String([Guid]::NewGuid().ToByteArray()).TrimEnd("=")
}

try {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TokenPath) | Out-Null
  Set-Content -LiteralPath $TokenPath -Value $Token -Encoding UTF8
} catch {
  Set-Content -LiteralPath $TempTokenPath -Value $Token -Encoding UTF8
  Write-Host "[02] Could not write web\config\server.token; wrote fallback token to $TempTokenPath"
}

$Process = Start-Process -FilePath $Python `
  -ArgumentList @("web\server\api_server.py", "--host", $HostName, "--port", "$Port", "--token", $Token) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -PassThru
Start-Sleep -Seconds 2
Write-Host "[02] Started python process id $($Process.Id)"

$Health = Test-Health $Token
Write-Host "[02] Health status: $($Health.StatusCode)"
Write-Host "[02] Console: http://$HostName`:$Port/web/console/"
Write-Host "[02] Token: $Token"
