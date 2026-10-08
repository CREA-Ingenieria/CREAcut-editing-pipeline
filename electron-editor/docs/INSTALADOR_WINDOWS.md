# Instalar CREACUT en Windows

[← Inicio](../../README.md) · [Downloads](../../README.md#downloads) · [Documentación](../../docs/README.md)

## Descargar e instalar

**Beta 0.2 · Windows x64**

[↓ Descargar CREAcut-Beta-0.2-Windows-x64.zip](https://github.com/CREA-Ingenieria/CREAcut-editing-pipeline/releases/download/v0.2.0-beta.1/CREAcut-Beta-0.2-Windows-x64.zip)

**Pendiente de publicación:** el enlace funcionará cuando el equipo publique la beta.

1. Cierra CREAcut, descomprime el `.zip` y abre `CREAcut-Beta-Setup-0.2.exe`
   con tu cuenta habitual de Windows.
2. Elige la carpeta de instalación.
3. Espera: el asistente prepara el backend y los modelos. Los detalles muestran
   el progreso.
4. Abre **CREAcut Beta** y confirma **Backend Python conectado**.

Usa Windows x64, Internet durante toda la instalación y espacio libre para el
backend y los modelos. No necesitas preparar Python, Node.js ni una `.venv`.

## Qué prepara el asistente

| Componente | Instalación |
|---|---|
| Interfaz Electron y React | Incluida en el instalador |
| Python 3.12 | CPython autónomo, sin tocar el Python que ya tengas |
| PyTorch, Whisper, FFmpeg y el resto | Descargados desde PyPI al instalar |
| Whisper `large-v3` y `medium` | Descargados para transcripción y alternativa por falta de VRAM |
| Ollama y Gemma 4 `gemma4` | Instala Ollama si falta y prepara el modelo configurado |

El entorno Python se crea en `%LOCALAPPDATA%\CREAcut\runtime`, fuera de la
carpeta de la aplicación. Así, actualizar CREAcut no obliga a descargarlo otra
vez: el asistente reutiliza el entorno si ya corresponde a esa versión.

### PyTorch: CPU por defecto, CUDA opcional

La instalación base usa **PyTorch para CPU**. Las bibliotecas CUDA ocupan unos
3,7 GB y solo sirven con una GPU NVIDIA compatible, así que no se instalan por
defecto: era el grueso del peso de las versiones anteriores.

Si el asistente detecta el controlador NVIDIA, ofrece el paquete CUDA durante la
instalación. Puedes añadirlo o quitarlo después desde la carpeta de instalación:

```powershell
# Añadir CUDA (acelera la transcripción; ~3,7 GB)
powershell -ExecutionPolicy Bypass -File "resources\backend-setup\install-gpu-pack.ps1"

# Volver al backend ligero: rehace el entorno con PyTorch CPU
powershell -ExecutionPolicy Bypass -File "resources\backend-setup\install-backend.ps1" -InstallDirectory "."
```

Sin CUDA, CREAcut transcribe con el procesador: funciona igual, pero tarda más
en clases largas.

[Modelos y cachés →](../../docs/modelos.md) · [Primer proyecto →](../../docs/GUIA_USUARIO.md)

## Si falla

El asistente permite **Reintentar** o **Cancelar**. Si cancelas, la instalación
queda incompleta. Un fallo del paquete CUDA no interrumpe la instalación: CREAcut
se queda con el backend CPU.

- **Sin conexión:** la instalación descarga las dependencias desde PyPI y los
  modelos desde sus orígenes. Necesita Internet de principio a fin.
- **Falta de espacio:** hacen falta varios GB para el entorno Python y los
  modelos, más lo que ocupe el paquete CUDA si lo aceptas.
- **Modelos:** consulta [Whisper y Gemma 4](../../docs/modelos.md).
- **Editor desconocido:** la beta todavía no tiene firma Authenticode; verifica el origen.
- **CUDA no aparece:** instala el paquete CUDA y comprueba que el controlador
  NVIDIA sea compatible; la aplicación informa el dispositivo real.
- **«El asistente no dejó preparado el backend»:** la instalación se interrumpió
  antes de terminar. Vuelve a ejecutar el instalador.

## Construir y publicar

Desde `electron-editor`, con el [entorno preparado](../../docs/installation.md):

```powershell
pnpm run dist:win
```

Resultado: **`electron-editor/dist/windows-release/CREAcut-Beta-0.2-Windows-x64.zip`**.
Ese `.zip` es el único archivo que se publica; `ARCHIVOS-PARA-PUBLICAR.txt` lo confirma.

El comando compila la aplicación, descarga `uv` para el asistente, construye el
instalador NSIS y lo comprime. No ejecuta PyInstaller: en Windows el backend ya
no se congela ni se incrusta. Si solo quieres repetir el empaquetado:

```powershell
pnpm run dist:win:installer
```

El instalador lleva la interfaz, las fuentes Python de CREAcut y `uv`; construye
el backend en la máquina del usuario. Por eso la entrega baja de varios GB a unos
cientos de MiB y no hay que trocear nada para respetar el
[límite de GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

A cambio, la instalación depende de PyPI y tarda más que copiar un backend ya
compilado. Compruébala en una cuenta sin el repositorio ni la `.venv` de
desarrollo antes de publicar.

[Comprobación y publicación manual →](../../docs/publicacion.md)

## Actualizar o desinstalar

Ejecuta el nuevo instalador para actualizar; el entorno Python se reutiliza si
corresponde a esa versión. Guarda tus proyectos fuera de la instalación.

Desinstala desde **Configuración → Aplicaciones → CREAcut Beta**. El desinstalador
pregunta si quieres **eliminar también los modelos Whisper y Gemma de CREAcut**;
la respuesta predeterminada es **No**. Si eliges **Sí**, elimina únicamente:

- Whisper `large-v3.pt` y `medium.pt` de `%USERPROFILE%\.cache\whisper`
  (o de `whisper` dentro de `XDG_CACHE_HOME`, si está configurado).
- Gemma `gemma4:latest`, mediante `ollama rm gemma4:latest` en el servidor local.
  Mantén Ollama abierto para que pueda procesar la eliminación.

Estos modelos pueden ser compartidos con otras aplicaciones. Se conservan los
demás modelos, Ollama y tus videos y proyectos guardados fuera de la instalación.
Las actualizaciones y las desinstalaciones silenciosas conservan los modelos y
no muestran esta pregunta. Para recuperar también el espacio del backend,
borra `%LOCALAPPDATA%\CREAcut\runtime`.

Si algún borrado falla, se muestra un aviso y la desinstalación continúa. Revisa
los detalles; si falla Gemma, abre Ollama y ejecuta `ollama rm gemma4:latest`.
El desinstalador no borra directamente el almacén de Ollama ni actúa sobre
servidores remotos. Si vuelves a usar Whisper, descargará el modelo que necesite;
para recuperar Gemma ejecuta `ollama pull gemma4`.

### Comprobación manual de la eliminación

Esta opción requiere construir e instalar el nuevo EXE; no aparece en los
desinstaladores generados anteriormente. Antes de publicar, comprueba en una
cuenta de prueba:

1. Instala el nuevo EXE sobre CREAcut: no debe preguntar por el borrado de modelos
   durante la actualización y debe conservarlos.
2. Desinstala eligiendo **No**: deben mantenerse ambos Whisper y Gemma.
3. Instala de nuevo, abre Ollama y desinstala eligiendo **Sí**: comprueba que
   faltan `large-v3.pt` y `medium.pt`, y que `ollama list` ya no muestra
   `gemma4:latest`. Los otros modelos (por ejemplo, Whisper `base`) deben seguir.
4. Comprueba también la ruta personalizada si usas `XDG_CACHE_HOME`. Con un
   archivo bloqueado o con Ollama cerrado, debe mostrarse el aviso de fallo y
   continuar la desinstalación, sin anunciar una limpieza completa.
