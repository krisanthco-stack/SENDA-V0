@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update_desktop.ps1"
if errorlevel 1 pause
