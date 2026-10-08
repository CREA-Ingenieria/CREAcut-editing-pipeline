# Empaquetado legado PySide6 para Windows

> Este documento describe el ejecutable anterior construido con PyInstaller.
> Para el instalador Electron actual, el acceso directo del escritorio y el
> archivo `CREAcut-Beta-Setup-0.2.exe`, consulta
> [`electron-editor/docs/INSTALADOR_WINDOWS.md`](../electron-editor/docs/INSTALADOR_WINDOWS.md).
> El instalador actual se identifica como Beta porque todavía no cuenta con una
> validación completa.

La aplicación PySide6 sigue este flujo:

`CREAcut.exe → seleccionar video → seleccionar guion .md → analizar → revisar en editor → exportar MP4`

No se debe proporcionar una transcripción de Whisper: CREAcut la genera localmente
durante el análisis. La primera ejecución descarga el modelo de Whisper elegido
por la configuración si todavía no está en la caché local, por lo que necesita
Internet. Las ejecuciones posteriores pueden reutilizar esa caché.

## Probar la aplicación desde el repositorio

En PowerShell, en la carpeta del proyecto:

```powershell
python -m pip install -e ".[whisper,ui]"
python -m creacut.ui
```

Selecciona el video, el guion Markdown y la carpeta donde se guardará el
proyecto `.creacut.json`. El botón **Analizar y abrir editor** crea únicamente
la propuesta editable: aún no genera el MP4 final.

En el editor, revisa la línea de tiempo y guarda las modificaciones. Finalmente
usa **Archivo → Exportar MP4…** para elegir el destino. Esa exportación usa las
decisiones guardadas y no vuelve a ejecutar Whisper ni la alineación.

## Crear el `CREAcut.exe` legado

El ejecutable se construye en modo `onedir`, que es más confiable para Qt,
OpenCV y FFmpeg que un único archivo comprimido.

```powershell
python -m pip install -e ".[desktop]"
.\scripts\build_windows_exe.ps1
```

El resultado es:

```text
dist\CREAcut\CREAcut.exe
```

Entrega la carpeta completa `dist\CREAcut`, no solo el `.exe`: contiene las
bibliotecas de Qt, FFmpeg y las dependencias nativas que necesita la aplicación.
El modelo Whisper no se incluye, porque puede ser grande y depende de la
configuración. CREAcut lo descarga y almacena automáticamente la primera vez
que se analiza un video.

Para personalizar chroma, overlays, modelo Whisper u otras opciones, coloca un
archivo `creacut.yml` junto a la aplicación desde la que la inicias, o usa el
flujo de línea de comandos para configuraciones especializadas.

## CUDA y Whisper

CREAcut detecta CUDA al iniciar una transcripción. Si está disponible, el log
indica, por ejemplo, `Whisper device: CUDA - NVIDIA GeForce RTX 4050 Laptop GPU`
y usa precisión FP16. Si no está disponible, indica explícitamente
`Whisper device: CPU - CUDA unavailable` y usa FP32.

Con la instalación de desarrollo en el entorno local, valida la GPU así:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.version.cuda); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
nvidia-smi
```

Mientras Whisper transcribe, abre otra consola y ejecuta `nvidia-smi -l 1`.
Debe aparecer `python.exe` usando memoria de la GPU. Si `large-v3` agota la
VRAM, CREAcut prueba `medium` en la misma GPU y lo deja registrado en el log;
nunca baja a CPU de forma silenciosa.

Para una comprobación corta y reproducible con un audio o video de prueba:

```powershell
.\.venv\Scripts\python.exe scripts\cuda_whisper_smoke.py .\prueba.mp4 --model base
```
