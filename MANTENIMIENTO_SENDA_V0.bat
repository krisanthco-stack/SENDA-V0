@echo off
:menu
cls
echo =====================================
echo SENDA.V0 0.4.6 - MANTENIMIENTO
echo =====================================
echo 1. Instalar / Reparar
echo 2. Actualizar sin borrar datos
echo 3. Desinstalar
echo 4. Extraer instalador desde GitHub
echo 5. Salir
set /p op=Seleccione: 
if "%op%"=="1" call "%~dp0INSTALAR_SENDA_V0.bat"
if "%op%"=="2" call "%~dp0ACTUALIZAR_SENDA_V0.bat"
if "%op%"=="3" call "%~dp0DESINSTALAR_SENDA_V0.bat"
if "%op%"=="4" call "%~dp0EXTRAER_INSTALADOR_GITHUB.bat"
if "%op%"=="5" exit /b 0
pause
goto menu
