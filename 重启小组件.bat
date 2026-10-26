@echo off
setlocal
cd /d "%~dp0"
if not exist "data\widget.lock" goto start
set /p OLD_PID=<"data\widget.lock"
if defined OLD_PID taskkill /F /PID %OLD_PID% >nul 2>nul
del /q "data\widget.lock" >nul 2>nul
:start
ping -n 2 127.0.0.1 >nul
start "" pythonw "src\desktop_widget.py"
