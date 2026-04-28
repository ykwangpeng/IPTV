Add-Type -AssemblyName System.IO.Compression.FileSystem
$ErrorActionPreference = "Stop"
Write-Output "Extracting Go 1.24.2 to C:\tools\go..."
[System.IO.Compression.ZipFile]::ExtractToDirectory("C:\tools\go124.zip", "C:\tools\go")
Remove-Item C:\tools\go124.zip -Force -ErrorAction SilentlyContinue
Write-Output "Extracted."

$env:PATH = "C:\tools\go\go\bin;$env:PATH"
$env:GOPROXY = "https://goproxy.cn,direct"
$v = & C:\tools\go\go\bin\go.exe version 2>&1
Write-Output "Go version: $v"

Write-Output "Installing blogwatcher..."
& C:\tools\go\go\bin\go.exe install github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest 2>&1 | Tee-Object -Variable OUT
Write-Output "Install output: $OUT"

Write-Output "Checking blogwatcher..."
$bw = & "$env:USERPROFILE\go\bin\blogwatcher.exe" --version 2>&1
Write-Output "blogwatcher: $bw"
Write-Output "DONE"
