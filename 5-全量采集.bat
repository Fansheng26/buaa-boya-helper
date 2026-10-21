@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found on PATH.
  echo.
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
python "src\step4_collect_all.py"
echo.
pause
