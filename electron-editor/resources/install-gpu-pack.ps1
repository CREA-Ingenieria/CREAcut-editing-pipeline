<#
    Sustituye el PyTorch CPU por la version con CUDA para acelerar Whisper en
    equipos con GPU NVIDIA.

    Es opcional a proposito: son unos 3,7 GB de bibliotecas CUDA que no sirven
    de nada sin una GPU compatible. El instalador lo ofrece cuando detecta
    nvidia-smi, y se puede ejecutar despues a mano desde la carpeta de
    instalacion, en resources\backend-setup.

    Para volver al backend ligero basta con reinstalar CREAcut: install-backend.ps1
    rehace el entorno con la version CPU.
#>
param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$env:UV_NO_PROGRESS = '1'
$env:UV_HTTP_TIMEOUT = '180'

try {
    $uv = Join-Path $PSScriptRoot 'uv.exe'
    if (!(Test-Path -LiteralPath $uv -PathType Leaf)) { throw "Falta $uv" }

    $manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') | ConvertFrom-Json
    if ($manifest.cudaIndex -notmatch '^https://') { throw 'Manifiesto del backend invalido.' }

    $venvPython = Join-Path $env:LOCALAPPDATA 'CREAcut\runtime\.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Falta el entorno del backend. Ejecuta primero el instalador de CREAcut.'
    }

    Write-Output 'Descargando PyTorch con CUDA. Son varios GB; puede tardar.'
    & $uv pip install --python $venvPython --index-url $manifest.cudaIndex --reinstall torch
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar PyTorch con CUDA.' }

    $verifyScript = Join-Path (Join-Path (Join-Path (Split-Path $PSScriptRoot -Parent) 'backend') 'python') 'verify_backend.py'
    & $venvPython $verifyScript --expect-cuda
    if ($LASTEXITCODE -ne 0) { throw 'El paquete CUDA quedo incompleto.' }
    Write-Output 'Paquete CUDA instalado.'
    exit 0
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    if (-not $Quiet) {
        Write-Output 'CREAcut seguira funcionando con el backend CPU.'
    }
    exit 1
}
