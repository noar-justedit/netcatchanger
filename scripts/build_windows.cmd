@echo off
rem ==========================================================================
rem  NetCatChanger - build the Windows installer
rem  Double-click this file ON WINDOWS. It produces:
rem      dist\NetCatChanger-Setup-<version>.exe
rem
rem  Needs Node.js (LTS) installed once: https://nodejs.org
rem  The first run downloads the build tools and Electron (about 150 MB, from
rem  GitHub). Electron is then kept in %LOCALAPPDATA%\NetCatChanger-build, so
rem  the next builds do not download it again.
rem ==========================================================================

rem  Double-clicked, a .cmd window closes the instant the script stops, and an
rem  error message vanishes with it. So the script reopens itself inside a
rem  console that stays open whatever happens.
if not defined NCC_BUILD_CONSOLE (
  set NCC_BUILD_CONSOLE=1
  cmd /k ""%~f0""
  exit /b
)

setlocal
title Build NetCatChanger (Windows)
cd /d "%~dp0.."

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [X] Node.js is not installed.
  echo      Install the LTS version from https://nodejs.org then run this file again.
  echo.
  goto :end
)

for /f "delims=" %%v in ('node -p "require('./package.json').version"') do set "VERSION=%%v"
echo.
echo  NetCatChanger %VERSION% - Windows installer
echo  ------------------------------------------
echo.

echo  [1/4] Installing the build tools...
if exist package-lock.json (
  call npm ci --no-audit --no-fund
) else (
  call npm install --no-audit --no-fund
)
if errorlevel 1 goto :failed

echo.
echo  [2/4] Getting Electron (about 150 MB the first time, then from the cache)...
rem  Downloaded by curl (built into Windows): it retries and resumes where it
rem  stopped, and the file is checked against Electron's published checksum.
rem  See scripts\fetch-electron.js for why neither Electron nor
rem  electron-builder is left to download it.
set "ELECTRON_DIR="
for /f "delims=" %%d in ('node scripts\fetch-electron.js') do set "ELECTRON_DIR=%%d"
if not defined ELECTRON_DIR goto :failed

echo.
echo  [3/4] Running the checks...
call npm test
if errorlevel 1 goto :failed

echo.
echo  [4/4] Building the installer...
call npm run build:win -- "-c.electronDist=%ELECTRON_DIR%"
if errorlevel 1 goto :failed

echo.
echo  [OK] dist\NetCatChanger-Setup-%VERSION%.exe
echo.
start "" explorer dist
goto :end

:failed
echo.
echo  [X] The build stopped. The message above says why.
echo.

:end
echo  You can close this window.
endlocal
exit /b 0
