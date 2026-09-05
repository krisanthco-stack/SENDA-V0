$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'
Write-Host 'SENDA.V0 - DESINSTALAR' -ForegroundColor Cyan
Write-Host '1. Desinstalar y CONSERVAR datos (recomendado)'
Write-Host '2. Desinstalar y ELIMINAR tambien todos los datos'
$choice=Read-Host 'Seleccione 1 o 2'
if ($choice -notin @('1','2')) { throw 'Opcion invalida.' }
Get-Process -Name 'SENDA.V0' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$desktop=[Environment]::GetFolderPath('Desktop')
Remove-Item (Join-Path $desktop 'SENDA.V0.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SENDA.V0') -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path $InstallRoot) { Remove-Item $InstallRoot -Recurse -Force }
if ($choice -eq '2') {
    $confirm=Read-Host 'Escriba ELIMINAR para borrar permanentemente la base, expedientes y respaldos'
    if ($confirm -ceq 'ELIMINAR') { if (Test-Path $DataRoot) { Remove-Item $DataRoot -Recurse -Force }; Write-Host 'Aplicacion y datos eliminados.' -ForegroundColor Yellow }
    else { Write-Host "Aplicacion eliminada. Datos CONSERVADOS en $DataRoot" -ForegroundColor Green }
} else { Write-Host "Aplicacion eliminada. Datos CONSERVADOS en $DataRoot" -ForegroundColor Green }
