@echo off
cd /d "%~dp0\.."

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install from https://python.org
    pause
    exit /b 1
)

python -m pip install pillow --quiet --disable-pip-version-check >nul 2>&1

net session >nul 2>&1
if errorlevel 1 (
    powershell -WindowStyle Hidden -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0..\" && python src\network_switcher.py' -Verb RunAs"
) else (
    python src\network_switcher.py
)
