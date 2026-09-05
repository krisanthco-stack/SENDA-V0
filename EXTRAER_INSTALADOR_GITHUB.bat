@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\extract_installer_from_github.ps1" -DestinationRoot "%CD%"
if errorlevel 1 (
  echo.
  echo No se pudo descargar o extraer el instalador desde GitHub. Revise el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo Instalador extraido correctamente. Revise la carpeta SENDA.V0_INSTALADOR_v* creada aqui.
pause
