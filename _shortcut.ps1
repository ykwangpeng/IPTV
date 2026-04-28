$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')

$sc = $ws.CreateShortcut("$desktop\VSCode.lnk")
$sc.TargetPath = "D:\VSCode\Code.exe"
$sc.WorkingDirectory = "D:\VSCode"
$sc.Save()
Write-Host "User desktop shortcut created: $desktop\VSCode.lnk"

$sc2 = $ws.CreateShortcut("C:\Users\Public\Desktop\VSCode.lnk")
$sc2.TargetPath = "D:\VSCode\Code.exe"
$sc2.WorkingDirectory = "D:\VSCode"
$sc2.Save()
Write-Host "Public desktop shortcut created"
