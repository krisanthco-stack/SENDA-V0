$ErrorActionPreference = 'Stop'

$SourceRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'
$PythonPathFile = Join-Path $InstallRoot 'python_path.txt'

function Ensure-XlrdVendor {
    $module = Join-Path $InstallRoot 'vendor\xlrd\__init__.py'
    if (Test-Path $module) { return }
    $url = 'https://files.pythonhosted.org/packages/1a/62/c8d562e7766786ba6587d09c5a8ba9f718ed3fa8af7f4553e8f91c36f302/xlrd-2.0.2-py2.py3-none-any.whl'
    $expected = 'EA762C3D29F4CCA48D82DF517B6D89FBCE4DB3107F9D78713E48CD321D5C9AA9'
    $wheel = Join-Path $env:TEMP 'senda_xlrd_2.0.2.whl'
    $zip = Join-Path $env:TEMP 'senda_xlrd_2.0.2.zip'
    try {
        Remove-Item $wheel,$zip -Force -ErrorAction SilentlyContinue
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            & $curl.Source --fail --location --retry 2 --connect-timeout 15 --max-time 120 --output $wheel $url
            if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar xlrd. Codigo curl: $LASTEXITCODE" }
        } else {
            Invoke-WebRequest -Uri $url -OutFile $wheel -UseBasicParsing -TimeoutSec 120
        }
        $actual = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actual -ne $expected) { throw 'El motor XLS descargado no coincide con el hash oficial esperado.' }
        Copy-Item $wheel $zip -Force
        Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $InstallRoot 'vendor') -Force
        if (-not (Test-Path $module)) { throw 'No se pudo instalar el motor XLS binario.' }
    } finally {
        Remove-Item $wheel,$zip -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host 'SENDA.V0 - ACTUALIZACION' -ForegroundColor Cyan
Write-Host "Paquete nuevo: $SourceRoot"
Write-Host "Aplicacion:    $InstallRoot"
Write-Host "Datos:         $DataRoot"
Write-Host 'La actualizacion reemplaza solo codigo de la aplicacion y preserva todos los datos del usuario.'

if (-not (Test-Path $InstallRoot)) {
    throw 'SENDA.V0 no esta instalada. Ejecute INSTALAR_SENDA_V0.bat primero.'
}
if ((Resolve-Path $SourceRoot).Path -eq (Resolve-Path $InstallRoot).Path) {
    throw 'Ejecute ACTUALIZAR_SENDA_V0.bat desde el paquete NUEVO, no desde la instalacion actual.'
}

# Barrera de seguridad: la carpeta de datos nunca puede estar dentro de la carpeta que se reemplaza.
$installFull = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$dataFull = [System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
if ($dataFull.StartsWith($installFull + '\', [System.StringComparison]::OrdinalIgnoreCase) -or $dataFull -eq $installFull) {
    throw 'Configuracion insegura: la carpeta de datos esta dentro de la carpeta de aplicacion. Actualizacion cancelada sin tocar datos.'
}

$folders = @('app','ui','vendor','scripts','assets','tools')
foreach ($name in $folders) {
    $src = Join-Path $SourceRoot $name
    if ($name -ne 'assets' -and -not (Test-Path $src)) { throw "Falta componente requerido: $name" }
    if (Test-Path $src) {
        $dst = Join-Path $InstallRoot $name
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $src $dst -Recurse -Force
    }
}

$files = @('INICIAR_SENDA_V0.bat','INSTALAR_SENDA_V0.bat','ACTUALIZAR_SENDA_V0.bat','DESINSTALAR_SENDA_V0.bat','MANTENIMIENTO_SENDA_V0.bat','pyproject.toml','README.md')
foreach ($name in $files) {
    $src = Join-Path $SourceRoot $name
    if (Test-Path $src) { Copy-Item $src (Join-Path $InstallRoot $name) -Force }
}

# Conservar la ruta de Python registrada durante la instalacion.
if (Test-Path $PythonPathFile) {
    $pythonExe = (Get-Content $PythonPathFile -Raw).Trim()
    if ($pythonExe -and (Test-Path $pythonExe)) {
        [Environment]::SetEnvironmentVariable('SENDA_V0_PYTHON', $pythonExe, 'User')
    }
}

# Verificar la version actualizada antes de declararla lista.
$runtimeExe = Join-Path $InstallRoot 'runtime\python\python.exe'
if (-not (Test-Path $runtimeExe)) {
    if (Test-Path $PythonPathFile) { $runtimeExe = (Get-Content $PythonPathFile -Raw).Trim() }
}
if (-not $runtimeExe -or -not (Test-Path $runtimeExe)) {
    throw 'No se encontro el runtime privado de SENDA.V0. Ejecute INSTALAR_SENDA_V0.bat para reparar la instalacion.'
}
Ensure-XlrdVendor
Push-Location $InstallRoot
try {
    Write-Host 'Verificando version actualizada (API + interfaz)...' -ForegroundColor Cyan
    & $runtimeExe -m app.launcher --check --no-browser --data-dir $DataRoot
    if ($LASTEXITCODE -ne 0) { throw 'La version actualizada no supero el autodiagnostico. Los datos del usuario permanecen intactos.' }
} finally { Pop-Location }

# IMPORTANTE: no existe ninguna operacion de borrado sobre $DataRoot en este actualizador.
Write-Host ''
Write-Host 'ACTUALIZACION COMPLETADA.' -ForegroundColor Green
Write-Host "Se preserva la base, expedientes, importaciones, respaldos, exportaciones y logs en: $DataRoot"
