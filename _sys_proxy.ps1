# Check Windows proxy settings
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$proxy = Get-ItemProperty $regPath -Name ProxyEnable -ErrorAction SilentlyContinue
Write-Host "ProxyEnable: $($proxy.ProxyEnable)"
$server = Get-ItemProperty $regPath -Name ProxyServer -ErrorAction SilentlyContinue
Write-Host "ProxyServer: $($server.ProxyServer)"
# Also check all listening ports
Write-Host ""
Write-Host "=== Listening ports ==="
netstat -ano | Select-String "LISTENING" | Select-Object -First 20
# Test the proxy server with curl
Write-Host ""
Write-Host "=== Test proxy ==="
$ErrorActionPreference = 'Continue'
try {
    $r = Invoke-WebRequest 'http://127.0.0.1:7890' -TimeoutSec 3 -UseBasicParsing
    Write-Host "7890 HTTP OK: $($r.StatusCode)"
} catch {
    Write-Host "7890 FAIL: $($_.Exception.Message)"
}
try {
    $r = Invoke-WebRequest 'http://127.0.0.1:1080' -TimeoutSec 3 -UseBasicParsing
    Write-Host "1080 HTTP OK: $($r.StatusCode)"
} catch {
    Write-Host "1080 FAIL: $($_.Exception.Message)"
}
