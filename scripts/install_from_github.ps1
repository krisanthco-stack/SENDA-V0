$ErrorActionPreference = 'Stop'

$Api = 'https://api.github.com/repos/krisanthco-stack/SENDA-V0/releases/latest'
$TempRoot = Join-Path $env:TEMP ("SENDA_V0_GITHUB_" + [Guid]::NewGuid().ToString('N'))
$ZipPath = Join-Path $TempRoot 'SENDA.V0_WINDOWS_DESKTOP.zip'
$ExtractRoot = Join-Path $TempRoot 'extract'
$DataRoot = Join-Path $env:LOCALAPPDATA 'SENDA.V0'

Write-Host 'SENDA.V0 - INSTALAR DESDE GITHUB' -ForegroundColor Cyan
Write-Host 'Descargando la ultima version publicada...' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null

$headers = @{ 'User-Agent' = 'SENDA.V0-Installer' }
$release = Invoke-RestMethod -Uri $Api -Headers $headers -TimeoutSec 60
$asset = $release.assets | Where-Object { $_.name -match '^SENDA\.V0_.*_WINDOWS_DESKTOP\.zip$' } | Select-Object -First 1
if (-not $asset) {
    throw 'La ultima Release no contiene el paquete SENDA.V0 Windows Desktop.'
}

Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $ZipPath -UseBasicParsing -TimeoutSec 300
if (-not (Test-Path $ZipPath) -or (Get-Item $ZipPath).Length -lt 100000) {
    throw 'La descarga del paquete de SENDA.V0 esta incompleta.'
}

Expand-Archive -Path $ZipPath -DestinationPath $ExtractRoot -Force
$installer = Get-ChildItem -Path $ExtractRoot -Filter install_desktop.ps1 -Recurse -File | Select-Object -First 1
if (-not $installer) {
    throw 'El paquete descargado no contiene scripts\install_desktop.ps1.'
}

Write-Host "Release: $($release.tag_name)" -ForegroundColor Green
Write-Host "Datos protegidos: $DataRoot" -ForegroundColor Green
Write-Host 'Cerrando SENDA.V0 para reemplazar únicamente los archivos del programa...' -ForegroundColor Cyan
Get-Process -Name 'SENDA.V0' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 900
& $installer.FullName
if ($LASTEXITCODE -ne 0) {
    throw "El instalador devolvio el codigo $LASTEXITCODE."
}

Write-Host 'Instalacion desde GitHub completada.' -ForegroundColor Green
try { Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue } catch { }
