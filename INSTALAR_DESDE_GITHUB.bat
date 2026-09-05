@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_from_github.ps1"
if errorlevel 1 (
  echo.
  echo La instalacion desde GitHub no pudo completarse. Revise el mensaje anterior.
  pause
  exit /b 1
)
