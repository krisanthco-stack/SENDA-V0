@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_desktop.ps1"
if errorlevel 1 (
 echo.
 echo La instalacion no pudo completarse. Revise el mensaje anterior.
 pause
 exit /b 1
)
