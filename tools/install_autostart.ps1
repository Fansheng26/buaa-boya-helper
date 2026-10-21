# Create a Startup shortcut that launches the desktop widget with pythonw.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command pythonw).Source
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "BoyaWidget.lnk"

$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = '"' + (Join-Path $root "src\desktop_widget.py") + '"'
$s.WorkingDirectory = $root
$s.WindowStyle = 7
$s.Save()

Write-Host "Autostart installed:"
Write-Host "  $lnk"
