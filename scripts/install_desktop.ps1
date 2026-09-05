$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'
$ExeName = 'SENDA.V0.exe'
$SourceExe = Join-Path $SourceRoot $ExeName
$TargetExe = Join-Path $InstallRoot $ExeName
$IconPath = $TargetExe

if (-not (Test-Path $SourceExe)) {
    throw "No se encontro $ExeName. Use el paquete WINDOWS_DESKTOP compilado desde GitHub Actions."
}

Write-Host 'SENDA.V0 0.4.6 - INSTALACION DE ESCRITORIO' -ForegroundColor Cyan
Write-Host "Aplicacion: $InstallRoot"
Write-Host "Datos:      $DataRoot"
Write-Host 'No abre Chrome ni Edge como navegador externo. Usa la misma UI HTML de GitHub dentro de una ventana propia WebView.'
Write-Host 'Los datos existentes se conservan fuera de la carpeta del programa.'

New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

# Replace application files only. Never delete or copy over DataRoot.
Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Path (Join-Path $SourceRoot '*') -Destination $InstallRoot -Recurse -Force

# GitHub/Windows can mark DLLs extracted from a downloaded ZIP as Internet files.
# Remove that mark before pythonnet/WebView2 loads Python.Runtime.dll.
Get-ChildItem -LiteralPath $InstallRoot -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Unblock-File -LiteralPath $TargetExe -ErrorAction SilentlyContinue

if (-not (Test-Path $TargetExe)) { throw 'La copia de SENDA.V0.exe fallo.' }

$env:SENDA_DATA_DIR = $DataRoot
& $TargetExe --check
if ($LASTEXITCODE -ne 0) { throw 'SENDA.V0 no supero el autodiagnostico local.' }

function New-SendaShortcut([string]$LinkPath,[string]$Description) {
    $shell=New-Object -ComObject WScript.Shell
    $s=$shell.CreateShortcut($LinkPath)
    $s.TargetPath=$TargetExe
    $s.WorkingDirectory=$InstallRoot
    $s.Description=$Description
    if (Test-Path $IconPath) { $s.IconLocation="$IconPath,0" }
    $s.Save()
}

$desktop=[Environment]::GetFolderPath('Desktop')
$start=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SENDA.V0'
New-Item -ItemType Directory -Force -Path $start | Out-Null
New-SendaShortcut (Join-Path $desktop 'SENDA.V0.lnk') 'SENDA.V0 - Aplicacion registral de escritorio'
New-SendaShortcut (Join-Path $start 'SENDA.V0.lnk') 'Abrir SENDA.V0'

Write-Host ''
Write-Host 'INSTALACION COMPLETADA.' -ForegroundColor Green
Write-Host 'SENDA funciona en una ventana propia de Windows, con la UI oficial HTML/CSS/JS y datos locales.'
Start-Process -FilePath $TargetExe -WorkingDirectory $InstallRoot
