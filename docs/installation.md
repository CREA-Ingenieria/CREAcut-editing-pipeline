# Instalación de CREAcut Beta

> **Estado beta `0.2.0-beta.1`:** la aplicación todavía no está probada por
> completo. Conserva copias de tus videos, guiones y proyectos.

## Si solo quieres usar la aplicación

No necesitas instalar Python, Node.js, pnpm, FFmpeg ni crear una `.venv`. El
instalador prepara la interfaz, el backend Python y FFmpeg. En Windows el
asistente construye el backend al instalar; en macOS, la primera vez que abres la app.

Solo necesitas:

- Windows x64 para el `.zip` con el instalador; o
- macOS Apple Silicon para el DMG `arm64`.

El EXE de Windows prepara Whisper y Gemma 4 durante la instalación, con conexión
a Internet. Consulta [Modelos](modelos.md) y la [guía de Windows](../electron-editor/docs/INSTALADOR_WINDOWS.md).
En macOS, la primera vez que abres la app se prepara Python, PyTorch, FFmpeg y
Whisper (unos 5 GB); Gemma requiere preparar Ollama según la [guía de macOS](../electron-editor/docs/INSTALADOR_MACOS.md).

## Windows: instalar el EXE

Archivo:

```text
CREAcut-Beta-Setup-0.2.exe
```

1. Cierra cualquier copia abierta de CREAcut.
2. Haz doble clic en el instalador.
3. Comprueba que el nombre sea **CREAcut Beta**.
4. Elige la carpeta, espera la preparación de Whisper y Gemma 4 y termina el asistente.
5. Abre **CREAcut Beta** desde el escritorio o el menú Inicio.
6. Confirma que la pantalla muestre **Backend Python conectado**.

El instalador no está firmado. SmartScreen puede mostrar “Editor desconocido”.
Continúa únicamente si reconoces el archivo que recibiste o construiste.

## macOS: instalar el DMG

El DMG es solo para Apple Silicon (M1 o posterior):

```text
CREAcut-Beta-0.2-arm64.dmg
```

1. Abre el DMG.
2. Arrastra **CREAcut Beta** a **Aplicaciones**.
3. Abre la aplicación desde Aplicaciones, Spotlight o Launchpad.
4. Si Gatekeeper la bloquea, verifica el origen, haz clic secundario sobre la
   aplicación y selecciona **Abrir**.
5. La primera vez aparece **Preparando CREAcut para tu Mac**; espera a que
   termine (requiere Internet).

Gemma es opcional; prepárala con los pasos de [Ollama en macOS](../electron-editor/docs/INSTALADOR_MACOS.md#gemma-4-opcional).

El DMG todavía no está firmado ni notarizado. No desactives Gatekeeper para
todo el sistema.

## Requisitos para desarrollar o construir instaladores

Esta sección es solo para quienes trabajan con el código. Aquí sí se utiliza
una `.venv`, pero esa carpeta no será necesaria en el equipo del usuario final.

- Python 3.11 o superior; Python 3.12 recomendado.
- Node.js LTS y pnpm.
- FFmpeg ya no hace falta en el `PATH` para ejecutar Whisper desde el código
  fuente: `imageio-ffmpeg`, que trae `requirements.txt`, lo provee. Los
  instaladores también preparan FFmpeg por su cuenta.
- Paquetes de `requirements.txt`.
- Espacio suficiente: PyTorch, Whisper y las bibliotecas multimedia hacen que
  el backend y el instalador sean grandes.

PowerPoint o LibreOffice son opcionales para convertir archivos `.pptx`. PDF y
carpetas de imágenes funcionan sin PowerPoint.

## Preparar el proyecto en Windows

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

Ejecutar desde el código:

```powershell
$env:CREACUT_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
pnpm dev
```

Construir el instalador autónomo:

```powershell
pnpm run dist:win
```

El proceso realiza tres pasos:

1. compila TypeScript y React;
2. descarga `uv`, la herramienta con la que el asistente creará el entorno Python;
3. electron-builder genera el EXE y el script lo comprime en un `.zip`.

No ejecuta PyInstaller: en Windows el backend se construye en la máquina del
usuario a partir de PyPI, no se incrusta en el instalador.

Resultado:

```text
electron-editor\dist\windows-release\
```

## Preparar el proyecto en macOS

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

Ejecutar desde el código:

```bash
export CREACUT_PYTHON="$(cd .. && pwd)/.venv/bin/python"
pnpm dev
```

Construir el DMG:

```bash
pnpm run dist:mac
```

El DMG lleva las fuentes de CREAcut y `uv`; no congela Python. Se construye en un
Mac con Apple Silicon, y `scripts/verify-bundle.mjs` hace fallar el empaquetado
si se cuela FFmpeg o cualquier binario de Python.

No se debe copiar una `.venv` de Windows a macOS.

## Archivos intermedios de construcción

Al construir aparecen carpetas regenerables:

- `electron-editor/.installer-build/`: `uv` y el manifiesto de preparación del entorno;
- `electron-editor/out/`: frontend compilado;
- `electron-editor/dist/`: instaladores y aplicaciones empaquetadas.

Estas carpetas no se versionan. No guardes proyectos personales dentro de
`dist/` porque puede reemplazarse en la siguiente construcción.

## Comprobación manual después de instalar

1. Abre CREAcut Beta sin el repositorio y sin activar una `.venv`.
2. Comprueba **Backend Python conectado**.
3. Revisa que el dispositivo mostrado sea el esperado.
4. Crea o abre un proyecto pequeño.
5. Reproduce el video y revisa transcripción, guion y timeline.
6. Importa un PDF o imágenes como diapositivas si usarás esa función.
7. Exporta un MP4 corto.
8. Cierra y vuelve a abrir la aplicación.

## Actualizar

Para usar una beta nueva, ejecuta su instalador sobre la versión anterior. Los
proyectos deben guardarse fuera de la carpeta de instalación.

Quien construye debe actualizar las dependencias y volver a ejecutar
`pnpm run dist:win` o `pnpm run dist:mac`; el backend se reconstruye en cada
ocasión.

## Desinstalar

- Windows: **Configuración → Aplicaciones → CREAcut Beta → Desinstalar**.
- macOS: mueve `CREAcut Beta.app` desde Aplicaciones a la Papelera.

Desinstalar la aplicación no elimina videos, proyectos ni modelos de Whisper
guardados en la cuenta del usuario.

## Limitaciones actuales

- Windows está configurado para x64.
- El DMG de macOS es solo para Apple Silicon (`arm64`).
- Los paquetes no están firmados ni notarizados.
- El tamaño final puede ser elevado por PyTorch, Whisper y bibliotecas de video.
- CUDA funciona únicamente si las bibliotecas incluidas y el controlador del
  equipo son compatibles. No se cambia silenciosamente a CPU tras un error de
  memoria.
- El DMG debe construirse y validarse realmente en macOS.
