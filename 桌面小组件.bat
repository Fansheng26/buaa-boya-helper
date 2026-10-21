@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python not found.
  pause
  exit /b 1
)
start "" pythonw "src\desktop_widget.py"
