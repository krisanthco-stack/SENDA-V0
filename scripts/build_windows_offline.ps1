$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Version = '0.3.0'
$RuntimeDir = Join-Path $Root 'runtime'
$RuntimeFile = "python-3.12.10-embed-amd64.zip"
$RuntimePath = Join-Path $RuntimeDir $RuntimeFile
$RuntimeUrl = "https://www.python.org/ftp/python/3.12.10/$RuntimeFile"
$Out = Join-Path $Root "SENDA.V0_${Version}_WINDOWS_OFFLINE.zip"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
if (-not (Test-Path $RuntimePath)) {
    Write-Host "Descargando runtime oficial de Python..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RuntimeUrl -OutFile $RuntimePath -UseBasicParsing -TimeoutSec 300
}
if ((Get-Item $RuntimePath).Length -lt 8000000) { throw 'Runtime descargado incompleto.' }
Push-Location $Root
try {
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'La suite de pruebas fallo.' }
    Remove-Item $Out -Force -ErrorAction SilentlyContinue
    $items = Get-ChildItem -Force | Where-Object { $_.Name -notin @('.git','.pytest_cache','SENDA.V0_0.3.0_WINDOWS_OFFLINE.zip') }
    Compress-Archive -Path $items.FullName -DestinationPath $Out -CompressionLevel Optimal
    Write-Host "Paquete offline creado: $Out" -ForegroundColor Green
} finally { Pop-Location }
