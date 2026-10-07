@echo off
rem NetCatChanger - publish this folder to GitHub. Double-click this file.
rem The work is done by push_github.ps1 (same folder); see its header.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_github.ps1"
