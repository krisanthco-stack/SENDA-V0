param(
    [string]$DestinationRoot = ''
)

$ErrorActionPreference = 'Stop'
$Api = 'https://api.github.com/repos/krisanthco-stack/SENDA-V0/releases/latest'
$TempRoot = Join-Path $env:TEMP ("SENDA_V0_EXTRACT_" + [Guid]::NewGuid().ToString('N'))
$ZipPath = Join-Path $TempRoot 'SENDA.V0_WINDOWS_DESKTOP.zip'

if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    $DestinationRoot = (Get-Location).Path
}
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)

Write-Host 'SENDA.V0 - EXTRAER INSTALADOR DESDE GITHUB' -ForegroundColor Cyan
Write-Host 'Consultando la Release mas reciente...' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try {
    $headers = @{ 'User-Agent' = 'SENDA.V0-Installer-Extractor' }
    $release = Invoke-RestMethod -Uri $Api -Headers $headers -TimeoutSec 60
    $asset = $release.assets | Where-Object { $_.name -match '^SENDA\.V0_.*_WINDOWS_DESKTOP\.zip$' } | Select-Object -First 1
    if (-not $asset) {
        throw 'La Release mas reciente no contiene SENDA.V0_*_WINDOWS_DESKTOP.zip.'
    }

    Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $ZipPath -UseBasicParsing -TimeoutSec 300
    if (-not (Test-Path $ZipPath) -or (Get-Item $ZipPath).Length -lt 100000) {
        throw 'La descarga del paquete Windows esta incompleta.'
    }

    $safeTag = ($release.tag_name -replace '[^A-Za-z0-9._-]', '_')
    if ([string]::IsNullOrWhiteSpace($safeTag)) { $safeTag = 'latest' }
    $ExtractRoot = Join-Path $DestinationRoot ("SENDA.V0_INSTALADOR_" + $safeTag)
    if (Test-Path $ExtractRoot) {
        Remove-Item -LiteralPath $ExtractRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractRoot -Force

    $installer = Get-ChildItem -Path $ExtractRoot -Filter 'INSTALAR_SENDA_V0.bat' -Recurse -File | Select-Object -First 1
    if (-not $installer) {
        throw 'El ZIP descargado no contiene INSTALAR_SENDA_V0.bat.'
    }

    Write-Host "Release encontrada: $($release.tag_name)" -ForegroundColor Green
    Write-Host "Paquete: $($asset.name)" -ForegroundColor Green
    Write-Host "Instalador extraido en: $ExtractRoot" -ForegroundColor Green
    Write-Host "Para instalar, abra esa carpeta y ejecute: $($installer.Name)" -ForegroundColor Yellow
    Write-Host 'Este script SOLO descarga y extrae; no instala ni modifica los datos de SENDA.' -ForegroundColor Cyan
}
finally {
    try { Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue } catch { }
}
