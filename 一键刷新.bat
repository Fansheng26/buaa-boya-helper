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
echo [1/2] 抓取博雅课程列表...
python "src\step5_boya_pages.py"
echo.
echo [2/2] 生成面板...
python "src\make_panel.py"
echo.
start "" "out\boya.html"
