NetCatChanger 2.0.1  -  by Just Edit
www.just-edit.fr
=========================================
Windows Network Profile Manager

REQUIREMENTS
------------
- Windows 10 / 11
- Python 3.8+  https://python.org  (check "Add to PATH")
- Inno Setup 6 (installed automatically by the build script)

HOW TO BUILD
------------
Double-click BUILD_windows.bat

The script does everything automatically:
  [1] Installs PyInstaller + Pillow via pip
  [2] Generates app_icon.ico
  [3] Compiles NetCatChanger.exe via PyInstaller
  [4] Installs Inno Setup via winget if not found
  [5] Compiles NetCatChanger_Setup.exe

OUTPUT
------
  NetCatChanger_Setup.exe   Windows installer (the one to distribute)
  dist\NetCatChanger.exe    Standalone exe (fallback if Inno Setup fails)

The installer:
  - Modern wizard UI
  - Installs to C:\Program Files\NetCatChanger
  - Optional Desktop shortcut
  - Start Menu shortcut
  - Registered in Add/Remove Programs with uninstaller
  - Launches the app at the end of install

RUN WITHOUT BUILDING
--------------------
Double-click Lancer_en_Admin.bat

DEBUG
-----
Double-click DEBUG.bat  (shows errors if the app crashes on launch)

FILES
-----
  network_switcher.py    Main application
  icons.py               Pre-rendered icons (no external deps at runtime)
  gen_icon.py            Generates app_icon.ico at build time
  installer.iss          Inno Setup script
  BUILD_windows.bat      Build script (exe + installer)
  Lancer_en_Admin.bat    Launch without building
  DEBUG.bat              Debug launcher
  *.svg                  Original icon sources (not used at runtime)
  app_icon.ico           Application icon (pre-generated)
  version_info.txt       Windows exe metadata
