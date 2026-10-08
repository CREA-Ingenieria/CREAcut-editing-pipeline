# Componentes de terceros

CREAcut se distribuye bajo la [GPL-3.0 o posterior](LICENSE). Usa componentes
de terceros que conservan sus propias licencias. Esta lista indica qué se
incluye en cada forma de distribución y bajo qué licencia.

## En el código fuente

| Componente | Ubicación | Licencia |
|---|---|---|
| Inter (fuente tipográfica) | `assets/fonts/Inter-Variable.ttf` | SIL Open Font License 1.1 — [`assets/fonts/OFL.txt`](assets/fonts/OFL.txt) |

## Editor Electron (instaladores de Windows y macOS)

| Componente | Licencia |
|---|---|
| Electron y Chromium | MIT; los avisos de Chromium viajan en `LICENSES.chromium.html` dentro del instalador |
| React, React DOM | MIT |
| Radix UI | MIT |
| lucide-react | ISC |
| Tailwind CSS, tailwind-merge, clsx | MIT |
| class-variance-authority | Apache-2.0 |
| Inter (`@fontsource-variable/inter`) | SIL Open Font License 1.1 |
| Lenis (desplazamiento suave) | MIT |

## Instaladores de Windows y macOS

Ninguno de los dos instaladores distribuye un Python ya armado ni FFmpeg. Ambos
incluyen `uv` (MIT o Apache-2.0) y las fuentes de CREAcut, y construyen el
entorno Python desde PyPI en el equipo de la persona: Windows durante la
instalación y macOS en el primer arranque. Esos componentes se descargan desde
sus orígenes y se rigen por sus propias licencias:

| Componente | Licencia |
|---|---|
| Python (CPython que gestiona `uv`) | PSF License |
| PyTorch | BSD-3-Clause |
| openai-whisper | MIT |
| MoviePy | MIT |
| imageio-ffmpeg y su binario de FFmpeg | BSD-2-Clause; el binario de FFmpeg es GPL |
| OpenCV (`opencv-python`) | Apache-2.0; la rueda incluye bibliotecas de FFmpeg |
| NumPy | BSD-3-Clause |
| Pillow | MIT-CMU |
| pypdfium2 y PDFium | Apache-2.0 o BSD-3-Clause; PDFium, BSD-3-Clause |
| python-pptx | MIT |
| Matplotlib | Matplotlib License (basada en la PSF) |
| PyYAML | MIT |
| ollama (cliente Python) | MIT |
| anthropic (cliente Python) | MIT |

En Windows, si falta, el instalador también descarga Ollama (MIT) desde
<https://ollama.com>.

## Modelos que se descargan al usar CREAcut

| Modelo | Licencia |
|---|---|
| Whisper (`large-v3`, `medium`) | MIT |
| Gemma 4 (vía Ollama) | Términos de uso de Gemma publicados por Google |
