$ErrorActionPreference = 'Stop'

$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'

Write-Host ''
Write-Host 'SENDA.V0 - DESINSTALAR' -ForegroundColor Yellow
Write-Host '1. Desinstalar SENDA.V0 y CONSERVAR los datos  [predeterminado]'
Write-Host '2. Desinstalar SENDA.V0 y ELIMINAR tambien todos los datos'
Write-Host '3. Cancelar'
$choice = Read-Host 'Seleccione 1, 2 o 3'
if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '1' }
if ($choice -eq '3') { Write-Host 'Operacion cancelada.'; exit 0 }
if ($choice -ne '1' -and $choice -ne '2') { throw 'Opcion invalida.' }

if ($choice -eq '2') {
    $confirm = Read-Host 'Escriba ELIMINAR para confirmar el borrado definitivo de la base y expedientes'
    if ($confirm -cne 'ELIMINAR') { throw 'No se confirmo el borrado de datos. No se realizaron cambios.' }
}

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenuFolder = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SENDA.V0'
$desktopLink = Join-Path $desktop 'SENDA.V0.lnk'
if (Test-Path $desktopLink) { Remove-Item $desktopLink -Force }
if (Test-Path $startMenuFolder) { Remove-Item $startMenuFolder -Recurse -Force }

# Quitar solo la referencia al runtime; no desinstalar Python porque puede usarlo otra aplicacion.
[Environment]::SetEnvironmentVariable('SENDA_V0_PYTHON', $null, 'User')

# Copiamos el limpiador a TEMP para poder eliminar la carpeta instalada incluso si este script se ejecuta desde ella.
$cleanup = Join-Path $env:TEMP ("senda_v0_cleanup_{0}.ps1" -f ([guid]::NewGuid().ToString('N')))
$deleteData = if ($choice -eq '2') { '$true' } else { '$false' }
$content = @"
Start-Sleep -Milliseconds 800
`$ErrorActionPreference = 'SilentlyContinue'
if (Test-Path '$($InstallRoot.Replace("'","''"))') { Remove-Item '$($InstallRoot.Replace("'","''"))' -Recurse -Force }
if ($deleteData -and (Test-Path '$($DataRoot.Replace("'","''"))')) { Remove-Item '$($DataRoot.Replace("'","''"))' -Recurse -Force }
Remove-Item -LiteralPath `$MyInvocation.MyCommand.Path -Force
"@
Set-Content -LiteralPath $cleanup -Value $content -Encoding UTF8
Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $cleanup + '"')) -WindowStyle Hidden

Write-Host ''
if ($choice -eq '2') {
    Write-Host 'DESINSTALACION PROGRAMADA: aplicacion y datos seran eliminados.' -ForegroundColor Yellow
} else {
    Write-Host 'DESINSTALACION PROGRAMADA: los datos se conservaran.' -ForegroundColor Green
    Write-Host "Datos conservados en: $DataRoot"
}
