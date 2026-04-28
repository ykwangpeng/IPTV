$ErrorActionPreference = "Stop"
Write-Output "Extracting Go"
Expand-Archive -Force C:\tools\go.zip C:\tools\go
Remove-Item C:\tools\go.zip -Force -ErrorAction SilentlyContinue
Write-Output "Done extracting."

$env:PATH = "C:\tools\go\go\bin;$env:PATH"
Write-Output ("Go version: " + (& C:\tools\go\go\bin\go.exe version 2>&1))

Write-Output "Installing blogwatcher"
& C:\tools\go\go\bin\go.exe install github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest
Write-Output "Done installing blogwatcher."

$goPath = "C:\tools\go\go\bin"
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$goPath*") {
    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$goPath", "User")
    Write-Output "Added to user PATH"
}
Write-Output "All done."
