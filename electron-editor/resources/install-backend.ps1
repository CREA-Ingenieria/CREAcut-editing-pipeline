<#
    Prepara el backend Python de CREAcut en la maquina del usuario.

    En lugar de incrustar un backend congelado de 4,6 GB en el instalador, se
    crea un entorno virtual y se instalan las dependencias desde PyPI. torch se
    toma del indice CPU de PyTorch: las bibliotecas CUDA suponian ~3,7 GB de esa
    cifra y solo sirven a quien tiene una GPU NVIDIA, que puede anadirlas
    despues con install-gpu-pack.ps1.

    El entorno vive fuera de la carpeta de instalacion, en %LOCALAPPDATA%, para
    que actualizar o reinstalar la aplicacion no obligue a descargarlo de nuevo.
#>
param(
    [Parameter(Mandatory = $true)][string]$InstallDirectory
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# uv escribe barras de progreso con secuencias ANSI que el registro de NSIS
# muestra como basura. El detalle util son las lineas de resumen.
$env:UV_NO_PROGRESS = '1'
$env:UV_HTTP_TIMEOUT = '180'

function Invoke-Step {
    param([string]$Executable, [string[]]$Arguments, [string]$FailureMessage)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

try {
    $setupRoot = $PSScriptRoot
    $backendRoot = Join-Path $InstallDirectory 'resources\backend'
    $uv = Join-Path $setupRoot 'uv.exe'
    $requirements = Join-Path (Join-Path $backendRoot 'python') 'requirements-runtime.txt'
    $verifyScript = Join-Path (Join-Path $backendRoot 'python') 'verify_backend.py'

    foreach ($required in @($uv, $requirements, $verifyScript)) {
        if (!(Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "El instalador esta incompleto: falta $required"
        }
    }

    $manifest = Get-Content -Raw -LiteralPath (Join-Path $setupRoot 'manifest.json') | ConvertFrom-Json
    if ($manifest.pythonVersion -notmatch '^3\.\d+$' -or $manifest.cpuIndex -notmatch '^https://') {
        throw 'Manifiesto del backend invalido.'
    }

    $runtime = Join-Path $env:LOCALAPPDATA 'CREAcut\runtime'
    $venv = Join-Path $runtime '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $marker = Join-Path $runtime 'backend.json'

    # Reutiliza un entorno ya preparado para la misma version: actualizar la
    # aplicacion no deberia volver a descargar cerca de 1 GB de ruedas.
    if ((Test-Path -LiteralPath $marker -PathType Leaf) -and (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        $installed = Get-Content -Raw -LiteralPath $marker | ConvertFrom-Json
        $usable = $false
        if ($installed.version -eq $manifest.version) {
            # Sin redirigir stderr: en PowerShell 5.1, redirigirlo desde un
            # ejecutable nativo con ErrorActionPreference 'Stop' aborta el
            # script. Aqui solo interesa el codigo de salida.
            & $venvPython $verifyScript | Out-Null
            $usable = $LASTEXITCODE -eq 0
        }
        if ($usable) {
            Write-Output "El backend $($manifest.version) ya estaba instalado. Se conserva."
            exit 0
        }
        Write-Output 'El entorno anterior no sirve para esta version. Se rehace.'
    }

    # Un CPython autonomo bajo LOCALAPPDATA: no depende de que el usuario tenga
    # Python instalado ni interfiere con el que ya tuviera.
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null

    if (Test-Path -LiteralPath $venv) {
        Remove-Item -LiteralPath $venv -Recurse -Force
    }

    # only-managed obliga a usar un CPython que uv descarga y guarda en
    # UV_PYTHON_INSTALL_DIR, nunca el que el usuario tenga instalado: asi el
    # entorno no se rompe si lo desinstala, lo actualiza o lo mueve.
    Write-Output "Preparando Python $($manifest.pythonVersion)..."
    Invoke-Step $uv @('venv', $venv, '--python', $manifest.pythonVersion, '--python-preference', 'only-managed') `
        'No se pudo preparar Python. Comprueba la conexion a Internet.'

    Write-Output 'Instalando PyTorch (version CPU, sin bibliotecas CUDA)...'
    Invoke-Step $uv @('pip', 'install', '--python', $venvPython, '--index-url', $manifest.cpuIndex, 'torch') `
        'No se pudo instalar PyTorch. Comprueba la conexion y el espacio libre.'

    Write-Output 'Instalando Whisper, FFmpeg y el resto de dependencias...'
    Invoke-Step $uv @('pip', 'install', '--python', $venvPython, '-r', $requirements) `
        'No se pudieron instalar las dependencias. Comprueba la conexion y el espacio libre.'

    # Comprueba lo que de verdad va a importar el backend, no solo que pip
    # terminara sin error. Va en un archivo y no en un -c porque PowerShell 5.1
    # maltrata las comillas al pasar un script multilinea a un ejecutable nativo.
    Write-Output 'Comprobando el entorno...'
    Invoke-Step $venvPython @($verifyScript) `
        'El entorno quedo incompleto: alguna dependencia no se puede importar.'

    Set-Content -LiteralPath $marker -Encoding utf8 -Value (ConvertTo-Json ([ordered]@{
        version = $manifest.version
        pythonVersion = $manifest.pythonVersion
        installedAt = (Get-Date).ToString('o')
    }))

    Write-Output 'Backend instalado. Preparando los modelos a continuacion...'
    exit 0
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    Write-Output 'Comprueba la conexion a Internet, el espacio libre y vuelve a intentarlo.'
    exit 1
}
