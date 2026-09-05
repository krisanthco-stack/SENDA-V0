@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0SENDA.V0.exe" (
  start "" "%~dp0SENDA.V0.exe"
  exit /b 0
)
if exist "%~dp0runtime\python\pythonw.exe" (
  start "" "%~dp0runtime\python\pythonw.exe" -m app.desktop_webview
  exit /b 0
)
echo SENDA.V0 Desktop no encuentra SENDA.V0.exe.
echo Use INSTALAR_SENDA_V0.bat o descargue el paquete Windows compilado.
pause
exit /b 1
