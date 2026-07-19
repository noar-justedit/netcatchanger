@echo off
cd /d "%~dp0\.."
title Build NetCatChanger 2.0.1
echo.
echo ==========================================
echo    NetCatChanger 2.0.1 - Build EXE
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Install from https://python.org and check "Add to PATH"
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

echo.
echo [1/3] Installing dependencies...
python -m pip install pyinstaller pillow --quiet --disable-pip-version-check
if errorlevel 1 ( echo [ERROR] pip failed. & pause & exit /b 1 )
echo [OK] Done.

echo.
echo [2/3] Generating icon...
python src\gen_icon.py
if errorlevel 1 ( echo [INFO] Skipped. ) else ( echo [OK] Done. )

echo.
echo [3/3] Compiling...
set ICON_OPT=
if exist assets\app_icon.ico set ICON_OPT=--icon=assets\app_icon.ico

python -m PyInstaller --onefile --windowed --name NetCatChanger --uac-admin %ICON_OPT% --add-data "src\icons.py;." src\network_switcher.py

if errorlevel 1 ( echo. & echo [ERROR] Build failed. & pause & exit /b 1 )

copy /y dist\NetCatChanger.exe NetCatChanger.exe >nul

echo.
echo Cleaning up...
if exist build rmdir /s /q build
if exist NetCatChanger.spec del /q NetCatChanger.spec

echo.
echo ==========================================
echo   DONE  -  NetCatChanger.exe
echo ==========================================
echo.
pause
