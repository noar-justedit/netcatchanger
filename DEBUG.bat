@echo off
cd /d "%~dp0"
echo === DEBUG MODE ===
echo.
python network_switcher.py
echo.
echo Exit code: %errorlevel%
pause
