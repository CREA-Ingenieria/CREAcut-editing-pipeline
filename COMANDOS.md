# Comandos rápidos de CREAcut Beta

Esta hoja sirve para copiar y pegar. Las explicaciones están en
[`docs/installation.md`](docs/installation.md).

> Versión actual: `0.2.0-beta.1`. No es una aplicación final ni está probada
> por completo. Conserva copias de tus proyectos y videos.

## Windows: preparar el proyecto para desarrollo y construcción

```powershell
cd "C:\ruta\a\CREAcut-editing-pipeline-main"
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

cd .\electron-editor
pnpm install
```

## Diapositivas: preparar el importador

Después de actualizar el proyecto, vuelve a instalar las dependencias Python
para incorporar el lector de PDF y la integración con PowerPoint en Windows:

```powershell
cd "C:\ruta\a\CREAcut-editing-pipeline-main"
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En el editor abre un proyecto y ve a **Inspector → Diapositivas**.
Puedes elegir un archivo `.pptx`, un PDF o una carpeta de imágenes. En Windows,
un PowerPoint instalado exporta el PPTX directamente a PNG; si no está
disponible, instala LibreOffice o exporta el archivo a PDF antes de importarlo.
Los PNG y sus miniaturas quedan junto al proyecto, en una carpeta
`<proyecto>.creacut-assets`.

Después de importarlas selecciona **Analizar y proponer**. CREAcut cruza el
texto de cada diapositiva con la transcripción y analiza cada PNG para ubicar
al presentador en el espacio menos ocupado. Revisa los tiempos y controles de
posición/anchura/altura; solo **Usar propuestas** activa las diapositivas para
el render MP4.

## Windows: ejecutar Electron

```powershell
cd "C:\ruta\a\CREAcut-editing-pipeline-main\electron-editor"
$env:CREACUT_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
pnpm dev
```

## Windows: crear el instalador

```powershell
cd "C:\ruta\a\CREAcut-editing-pipeline-main\electron-editor"
pnpm run dist:win
```

Salida: `dist\windows-release\CREAcut-Beta-0.2-Windows-x64.zip`, el único
archivo que se publica. `ARCHIVOS-PARA-PUBLICAR.txt` lo confirma. El usuario
final no necesita `.venv`.

El comando no ejecuta PyInstaller: en Windows el backend ya no se congela. El
instalador lleva la interfaz, las fuentes Python y `uv`, y construye el entorno
desde PyPI en la máquina del usuario. Para repetir solo el empaquetado:

```powershell
pnpm run dist:win:installer
```

Para comprobarlo antes de publicar, descomprime el `.zip` y ejecuta el EXE en
una cuenta sin el repositorio ni la `.venv`. Necesitas Internet durante toda la
instalación. [Detalles del empaquetado](electron-editor/docs/INSTALADOR_WINDOWS.md#construir-y-publicar).

## macOS: preparar el proyecto para desarrollo y construcción

```bash
cd /ruta/a/CREAcut-editing-pipeline-main
brew install python@3.12 node pnpm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

cd electron-editor
pnpm install
```

## Diapositivas: preparar el importador

```bash
cd /ruta/a/CREAcut-editing-pipeline-main
source .venv/bin/activate
python -m pip install -r requirements.txt
```

En **Inspector → Diapositivas**, importa un PDF o una carpeta de
imágenes. Para importar un `.pptx` sin PowerPoint, instala LibreOffice o
exporta primero el archivo a PDF. Los originales no se modifican.

## macOS: ejecutar Electron

```bash
cd /ruta/a/CREAcut-editing-pipeline-main/electron-editor
export CREACUT_PYTHON="$(cd .. && pwd)/.venv/bin/python"
pnpm dev
```

## macOS: crear el DMG

```bash
cd /ruta/a/CREAcut-editing-pipeline-main/electron-editor
pnpm run dist:mac
```

Salida: `dist/CREAcut-Beta-0.2-arm64.dmg` (solo Apple Silicon). El DMG lleva las
fuentes y `uv`; el usuario final no necesita `.venv`.

## CLI: crear un proyecto editable

```bash
creacut video.mp4 --script guion.md \
  --project-only --project-output video.creacut.json --verbose
```

## CLI: ejecutar análisis y render en un solo paso

```bash
creacut video.mp4 --script guion.md --output video-final.mp4 --verbose
```

## CLI: renderizar un proyecto revisado

```bash
creacut render-project video.creacut.json \
  --output video-final.mp4 --verbose
```

## Verificación

```bash
python --version
creacut --help
python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

Desde `electron-editor`:

```bash
pnpm run typecheck
pnpm run build
```

## CUDA en Windows

```powershell
& ..\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
nvidia-smi
```

Mientras Whisper trabaja:

```powershell
nvidia-smi -l 1
```

## Editor legado PySide6

Solo si necesitas la interfaz anterior:

```bash
python -m pip install -e ".[ui]"
creacut-editor
```
