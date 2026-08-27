@echo off
cd /d "%~dp0\.."
title Build NetCatChanger 2.2.1
echo.
echo ==========================================
echo    NetCatChanger 2.2.1 - Build EXE
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
python -m pip install pyinstaller pillow pystray --quiet --disable-pip-version-check
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

set VER_OPT=
if exist src\version_info.txt set VER_OPT=--version-file=src\version_info.txt

python -m PyInstaller --onefile --windowed --name NetCatChanger --uac-admin %ICON_OPT% %VER_OPT% --collect-submodules pystray --add-data "src\icons.py;." --add-data "src\fonts\Poppins-Bold.ttf;fonts" src\network_switcher.py

if errorlevel 1 ( echo. & echo [ERROR] Build failed. & pause & exit /b 1 )

copy /y dist\NetCatChanger.exe NetCatChanger.exe >nul

echo.
echo [4/4] Building Windows installer...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
where iscc >nul 2>&1 && set "ISCC=iscc"

if defined ISCC (
    "%ISCC%" /Qp installer\installer.iss
    if errorlevel 1 ( echo [ERROR] Installer build failed. & pause & exit /b 1 )
    echo [OK] dist\NetCatChanger-Setup-2.2.1.exe
) else (
    echo [INFO] Inno Setup not found - installer skipped.
    echo        Install it from https://jrsoftware.org/isinfo.php and re-run
    echo        this script to also get NetCatChanger-Setup-2.2.1.exe
)

echo.
echo Cleaning up...
if exist build rmdir /s /q build
if exist NetCatChanger.spec del /q NetCatChanger.spec

echo.
echo ==========================================
echo   DONE
echo     portable : NetCatChanger.exe
echo     installer: dist\NetCatChanger-Setup-2.2.1.exe
echo ==========================================
echo.
pause
