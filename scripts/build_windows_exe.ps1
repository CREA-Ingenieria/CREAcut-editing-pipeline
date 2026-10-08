# Build the local Windows desktop distribution in .\dist\CREAcut\CREAcut.exe.
# Run from a virtual environment that has installed: pip install -e ".[desktop]"

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name CREAcut `
        --collect-all PySide6 `
        --collect-all imageio_ffmpeg `
        --collect-all whisper `
        --hidden-import PySide6.QtMultimedia `
        --hidden-import PySide6.QtMultimediaWidgets `
        scripts/creacut_desktop.py

    Write-Host "Listo: $projectRoot\dist\CREAcut\CREAcut.exe"
}
finally {
    Pop-Location
}
