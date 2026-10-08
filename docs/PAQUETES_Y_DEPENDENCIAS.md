# Paquetes y dependencias de CREAcut Beta

CREAcut combina Python para procesar video y Electron/React para mostrar la
interfaz. Quien instala el `.exe` o `.dmg` no tiene que instalar estas piezas
por separado: el instalador prepara lo necesario para ejecutar la aplicación.

## Usuario final

| Elemento | ¿Debe instalarlo? | Explicación |
|---|---:|---|
| Python | No | El instalador (Windows) o el primer arranque (macOS) lo descarga con `uv`. |
| `.venv` | No | Solo se utiliza para construir. |
| FFmpeg | No | Viene con `imageio-ffmpeg` desde PyPI al preparar el entorno. |
| Node.js y pnpm | No | Electron ya está compilado. |
| Modelos de Whisper | Automático | El EXE de Windows los prepara al instalar; en macOS, el primer arranque. |
| Ollama y Gemma 4 | Automático en Windows | El EXE prepara el modelo gemma4 y, si falta, instala Ollama. [Detalles](modelos.md). |

El usuario sí debe elegir un instalador compatible: Windows x64 o macOS con
Apple Silicon.

## Equipo de desarrollo

Para modificar o construir CREAcut se necesita:

- Python 3.11 o superior;
- una `.venv` local;
- Node.js LTS y pnpm;
- los paquetes de `requirements.txt`;
- espacio para PyTorch, Whisper, el backend y los instaladores.

Para transcribir con Whisper desde el código fuente no hace falta `ffmpeg` en el
`PATH`: CREAcut decodifica el audio por su cuenta. Los instaladores preparan el
FFmpeg de `imageio-ffmpeg` en el equipo del usuario.

## Paquetes Python

La fuente de verdad del Core es `pyproject.toml`. `requirements.txt` prepara la
estación completa; los instaladores no la usan.

| Paquete | Para qué sirve |
|---|---|
| `moviepy` | Composición y codificación de clips. |
| `imageio-ffmpeg` | Binario de FFmpeg; se descarga desde PyPI al preparar el entorno. |
| `opencv-python` | Imagen, chroma y análisis visual. |
| `numpy` | Cálculo numérico, audio e imagen. |
| `Pillow` | Imágenes y tarjetas. |
| `pypdfium2` | Conversión de páginas PDF. |
| `python-pptx` | Lectura del texto de PowerPoint. |
| `pywin32` | Exportación directa mediante PowerPoint en Windows. |
| `matplotlib` | Ecuaciones y gráficos. |
| `PyYAML` | Configuración `.yml`. |
| `openai-whisper` | Transcripción automática. |
| `ollama`, `anthropic` | Proveedores opcionales para extraer listas. |
| `PyInstaller` | Solo el empaquetado del editor anterior PySide6. |
| `PySide6` | Editor anterior; no se incluye en el backend Electron. |

Los extras de `pyproject.toml` permiten instalaciones más pequeñas:

| Extra | Uso |
|---|---|
| `whisper` | Core con transcripción. |
| `llm` | Clientes Ollama y Anthropic. |
| `ui` | Editor legado PySide6. |
| `desktop` | Empaquetado legado PySide6. |
| `all` | Whisper y clientes LLM. |
| `dev` | Pruebas Python. |

## Paquetes Electron

La fuente de verdad es `electron-editor/package.json`.

### Aplicación

| Paquete | Para qué sirve |
|---|---|
| `electron` | Ventana y procesos de escritorio. |
| `react`, `react-dom` | Componentes y estado de la interfaz. |
| `@electron-toolkit/utils` | Utilidades de Electron. |
| `lucide-react` | Iconos. |
| `@radix-ui/*` | Controles accesibles. |
| `@fontsource-variable/inter` | Tipografía incluida. |
| `lenis` | Desplazamiento suave de la bienvenida. |
| `clsx`, `tailwind-merge`, `class-variance-authority` | Variantes de estilos. |

### Construcción

| Paquete | Para qué sirve |
|---|---|
| `typescript` | Comprobación estática. |
| `vite`, `electron-vite` | Compilación del frontend. |
| `tailwindcss` | Estilos. |
| `electron-builder` | Instalador `.exe`, aplicación `.app` y DMG. |
| `vitest` | Pruebas existentes del frontend. |

## Cómo se construyen los instaladores

Ningún instalador congela Python. Ambos llevan las fuentes de `creacut/` y
`electron-editor/python/`, más `uv`, y arman el entorno desde PyPI en el equipo
del usuario:

- Windows: durante la instalación NSIS, con `resources/install-backend.ps1`.
- macOS: en el primer arranque, con `src/main/macos-backend-setup.ts`.

Por eso CREA no redistribuye FFmpeg ni otros binarios de terceros con
obligaciones de código fuente. Para evitar que se cuelen, `scripts/verify-bundle.mjs`
revisa el DMG durante el empaquetado y lo hace fallar si encuentra FFmpeg,
bibliotecas nativas o `site-packages`. Electron ejecuta el backend desde el
entorno preparado y ya no usa `backend-location.json`.

## Comandos

```bash
# Preparar el desarrollo
python -m pip install -r requirements.txt
python -m pip install -e .

# Preparar Electron
cd electron-editor
pnpm install
pnpm run typecheck
```

Construir Windows:

```powershell
pnpm run dist:win
```

Construir macOS:

```bash
pnpm run dist:mac
```

## Qué no debe mezclarse

- La `.venv` es una herramienta de construcción, no un requisito del usuario.
- `pip` prepara el backend; `pnpm` prepara la interfaz.
- electron-builder crea el instalador; el entorno Python se arma en el equipo del usuario.
- El backend de Windows no funciona en macOS ni viceversa.
- El DMG de macOS es solo para Apple Silicon (arm64).
- Los modelos de Whisper son datos de usuario y no código del instalador.
