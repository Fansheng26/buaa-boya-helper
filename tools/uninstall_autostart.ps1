# Remove the Startup shortcut created by install_autostart.ps1
$ErrorActionPreference = "Stop"
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "BoyaWidget.lnk"
if (Test-Path $lnk) {
    Remove-Item $lnk -Force
    Write-Host "Autostart removed."
} else {
    Write-Host "Autostart was not installed."
}
