param(
  [string]$SceneId = "scene_a",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8080,
  [int]$Seconds = 12
)

$ManifestUrl = "/web/generated/websplatserve/$SceneId/manifest.json"

Write-Host "[07] Browser URLs"
Write-Host "Viewer:"
Write-Host "http://$HostName`:$Port/web/viewers/progressive.html?url=$ManifestUrl&policy=joint&profile=auto"
Write-Host ""
Write-Host "Browser QoE benchmark:"
Write-Host "http://$HostName`:$Port/web/viewers/benchmark.html?url=$ManifestUrl&seconds=$Seconds"
Write-Host ""
Write-Host "This benchmark records TTFR, bytes, resident rows, chunk arrivals, FPS/P95, client profile, capability, and failures."
Write-Host "It does not run PSNR/SSIM/LPIPS or image-quality evaluation."

