@echo off
cd /d "%~dp0\.."
echo === DEBUG MODE ===
echo.
python src\network_switcher.py
echo.
echo Exit code: %errorlevel%
pause
