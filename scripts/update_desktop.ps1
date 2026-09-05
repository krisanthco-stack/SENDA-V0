$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'
$SourceExe = Join-Path $SourceRoot 'SENDA.V0.exe'
$TargetExe = Join-Path $InstallRoot 'SENDA.V0.exe'
if (-not (Test-Path $SourceExe)) { throw 'El paquete de actualizacion no contiene SENDA.V0.exe.' }
if (([IO.Path]::GetFullPath($DataRoot)).StartsWith([IO.Path]::GetFullPath($InstallRoot),[StringComparison]::OrdinalIgnoreCase)) { throw 'Proteccion: los datos no pueden estar dentro de la carpeta del programa.' }
Write-Host 'Actualizando SENDA.V0...' -ForegroundColor Cyan
Write-Host "Datos protegidos: $DataRoot" -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Get-Process -Name 'SENDA.V0' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Path (Join-Path $SourceRoot '*') -Destination $InstallRoot -Recurse -Force
# Remove Mark-of-the-Web before the updated WebView/pythonnet runtime starts.
Get-ChildItem -LiteralPath $InstallRoot -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Unblock-File -LiteralPath $TargetExe -ErrorAction SilentlyContinue
if (-not (Test-Path $TargetExe)) { throw 'Actualizacion incompleta.' }
$env:SENDA_DATA_DIR=$DataRoot
& $TargetExe --check
if ($LASTEXITCODE -ne 0) { throw 'La nueva version no supero el autodiagnostico.' }
$logDir=Join-Path $DataRoot 'logs';New-Item -ItemType Directory -Force -Path $logDir | Out-Null
"$(Get-Date -Format s) Actualizacion de aplicacion completada; datos preservados." | Add-Content (Join-Path $logDir 'updates.log')
Write-Host 'ACTUALIZACION COMPLETADA. Los datos cargados no fueron modificados.' -ForegroundColor Green
Start-Process -FilePath $TargetExe -WorkingDirectory $InstallRoot
