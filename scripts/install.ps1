$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'

$SourceRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\SENDA.V0'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'
$RuntimeRoot = Join-Path $InstallRoot 'runtime\python'
$RuntimeExe = Join-Path $RuntimeRoot 'python.exe'
$PythonPathFile = Join-Path $InstallRoot 'python_path.txt'
$IconPath = Join-Path $InstallRoot 'assets\senda_v0.ico'

function Get-EmbeddedPythonPackage {
    $version = '3.12.10'
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($arch -eq 'ARM64') {
        $file = "python-$version-embed-arm64.zip"
    } elseif ($arch -eq 'x86') {
        $file = "python-$version-embed-win32.zip"
    } else {
        $file = "python-$version-embed-amd64.zip"
    }
    return @{
        Version = $version
        File = $file
        Url = "https://www.python.org/ftp/python/$version/$file"
    }
}

function Download-FileWithTimeout {
    param(
        [Parameter(Mandatory=$true)][string]$Url,
        [Parameter(Mandatory=$true)][string]$Destination
    )
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        Write-Host 'Descargando runtime integrado de SENDA (aprox. 11 MB)...' -ForegroundColor Cyan
        & $curl.Source --fail --location --retry 2 --connect-timeout 15 --max-time 300 --output $Destination $Url
        if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar el runtime integrado. Codigo curl: $LASTEXITCODE" }
        return
    }

    Write-Host 'Descargando runtime integrado de SENDA...' -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 300
}

function Configure-EmbeddedPython {
    $pth = Get-ChildItem -Path $RuntimeRoot -Filter 'python*._pth' -File | Select-Object -First 1
    $stdlib = Get-ChildItem -Path $RuntimeRoot -Filter 'python*.zip' -File | Select-Object -First 1
    if (-not $pth -or -not $stdlib) {
        throw 'El runtime descargado de Python no tiene la estructura esperada.'
    }
    @(
        $stdlib.Name,
        '.',
        '..\..',
        '..\..\vendor',
        'import site'
    ) | Set-Content -LiteralPath $pth.FullName -Encoding ASCII
}

function Ensure-EmbeddedPython {
    if (Test-Path $RuntimeExe) {
        try {
            & $RuntimeExe -c "import sys; assert sys.version_info >= (3,10); print(sys.version)" | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host 'Runtime integrado de SENDA: OK' -ForegroundColor Green
                return $RuntimeExe
            }
        } catch {}
        Write-Host 'Runtime integrado incompleto. Se reconstruira.' -ForegroundColor Yellow
        Remove-Item $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    $package = Get-EmbeddedPythonPackage
    $download = Join-Path $env:TEMP ("senda_v0_{0}" -f $package.File)
    $bundled = Join-Path $SourceRoot ("runtime\{0}" -f $package.File)
    try {
        Remove-Item $download -Force -ErrorAction SilentlyContinue
        if (Test-Path $bundled) {
            Write-Host 'Usando runtime integrado incluido en el paquete...' -ForegroundColor Cyan
            Copy-Item $bundled $download -Force
        } else {
            Download-FileWithTimeout -Url $package.Url -Destination $download
        }
        if (-not (Test-Path $download)) { throw 'La descarga del runtime no creo el archivo esperado.' }
        $size = (Get-Item $download).Length
        if ($size -lt 8000000) { throw "Descarga incompleta del runtime ($size bytes)." }

        New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
        Expand-Archive -LiteralPath $download -DestinationPath $RuntimeRoot -Force
        Configure-EmbeddedPython

        & $RuntimeExe -c "import sys; assert sys.version_info >= (3,10); print(sys.executable)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'El runtime integrado no pudo ejecutarse.' }
        return $RuntimeExe
    } catch {
        Remove-Item $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw "No se pudo preparar el runtime integrado de SENDA.V0. Verifique Internet y vuelva a ejecutar el instalador. Detalle: $($_.Exception.Message)"
    } finally {
        Remove-Item $download -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-XlrdVendor {
    $module = Join-Path $InstallRoot 'vendor\xlrd\__init__.py'
    if (Test-Path $module) {
        Write-Host 'Motor XLS binario incluido: OK' -ForegroundColor Green
        return
    }
    $url = 'https://files.pythonhosted.org/packages/1a/62/c8d562e7766786ba6587d09c5a8ba9f718ed3fa8af7f4553e8f91c36f302/xlrd-2.0.2-py2.py3-none-any.whl'
    $expected = 'EA762C3D29F4CCA48D82DF517B6D89FBCE4DB3107F9D78713E48CD321D5C9AA9'
    $wheel = Join-Path $env:TEMP 'senda_xlrd_2.0.2.whl'
    $zip = Join-Path $env:TEMP 'senda_xlrd_2.0.2.zip'
    try {
        Write-Host 'Preparando motor XLS binario de SENDA...' -ForegroundColor Cyan
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
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot 'vendor') | Out-Null
        Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $InstallRoot 'vendor') -Force
        if (-not (Test-Path $module)) { throw 'No se pudo instalar el motor XLS binario.' }
    } finally {
        Remove-Item $wheel,$zip -Force -ErrorAction SilentlyContinue
    }
}

function New-SendaShortcut {
    param(
        [Parameter(Mandatory=$true)][string]$LinkPath,
        [Parameter(Mandatory=$true)][string]$Target,
        [string]$Description = 'SENDA.V0'
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($LinkPath)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = $Description
    if (Test-Path $IconPath) { $shortcut.IconLocation = "$IconPath,0" }
    $shortcut.Save()
}

Write-Host ''
Write-Host 'SENDA.V0 - INSTALACION AUTOCONTENIDA' -ForegroundColor Cyan
Write-Host "Origen:      $SourceRoot"
Write-Host "Aplicacion:  $InstallRoot"
Write-Host "Datos:       $DataRoot"
Write-Host 'SENDA instalara su propio runtime privado. NO usa winget, Microsoft Store ni Python del sistema.'
Write-Host 'Los datos permanecen separados y se conservan al actualizar.'

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

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

$pythonExe = Ensure-EmbeddedPython
Ensure-XlrdVendor
Write-Host "Runtime SENDA: $pythonExe" -ForegroundColor Green
Set-Content -Path $PythonPathFile -Value $pythonExe -Encoding Default
[Environment]::SetEnvironmentVariable('SENDA_V0_PYTHON', $pythonExe, 'User')

Push-Location $InstallRoot
try {
    & $pythonExe -c "import app.server, app.launcher; import openpyxl, xlsxwriter, xlrd; print('SENDA.V0 runtime OK')"
    if ($LASTEXITCODE -ne 0) { throw 'El runtime integrado existe, pero SENDA.V0 no pudo cargar sus componentes.' }
    Write-Host 'Verificando servidor + interfaz antes de crear accesos directos...' -ForegroundColor Cyan
    & $pythonExe -m app.launcher --check --no-browser --data-dir $DataRoot
    if ($LASTEXITCODE -ne 0) { throw 'SENDA.V0 no supero el autodiagnostico de API + interfaz. No se crearan accesos directos.' }
} finally {
    Pop-Location
}

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenuFolder = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SENDA.V0'
New-Item -ItemType Directory -Force -Path $startMenuFolder | Out-Null

New-SendaShortcut -LinkPath (Join-Path $desktop 'SENDA.V0.lnk') -Target (Join-Path $InstallRoot 'INICIAR_SENDA_V0.bat') -Description 'SENDA.V0 - Gestion registral local'
New-SendaShortcut -LinkPath (Join-Path $startMenuFolder 'SENDA.V0.lnk') -Target (Join-Path $InstallRoot 'INICIAR_SENDA_V0.bat') -Description 'Abrir SENDA.V0'
New-SendaShortcut -LinkPath (Join-Path $startMenuFolder 'Actualizar SENDA.V0.lnk') -Target (Join-Path $InstallRoot 'ACTUALIZAR_SENDA_V0.bat') -Description 'Actualizar SENDA.V0 sin borrar datos'
New-SendaShortcut -LinkPath (Join-Path $startMenuFolder 'Desinstalar SENDA.V0.lnk') -Target (Join-Path $InstallRoot 'DESINSTALAR_SENDA_V0.bat') -Description 'Desinstalar SENDA.V0'

Write-Host ''
Write-Host 'INSTALACION COMPLETADA.' -ForegroundColor Green
Write-Host 'SENDA.V0 ya tiene su propio runtime y no depende de Python instalado en Windows.'
Write-Host 'Se creo el acceso directo SENDA.V0 en el escritorio y menu Inicio.'
Write-Host "Datos preservados en: $DataRoot"
Write-Host ''
Write-Host 'Abriendo SENDA.V0...'
Start-Process -FilePath (Join-Path $InstallRoot 'INICIAR_SENDA_V0.bat') -WorkingDirectory $InstallRoot
