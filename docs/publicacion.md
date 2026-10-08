# Construir y publicar la beta 0.2

[← Documentación](README.md)

El equipo realiza el commit, las comprobaciones y la publicación manualmente.

## Archivos de la entrega

**Versión técnica:** `0.2.0-beta.1` · **Tag:** `v0.2.0-beta.1`

| Sistema | Salida dentro de `electron-editor/dist/` | Comando |
|---|---|---|
| Windows x64 | `windows-release/CREAcut-Beta-0.2-Windows-x64.zip` | `pnpm run dist:win` |
| macOS Apple Silicon | `CREAcut-Beta-0.2-arm64.dmg` | `pnpm run dist:mac` en un Mac con Apple Silicon |

Prepara el [entorno](installation.md) y ejecuta desde `electron-editor` en el
sistema correspondiente. El DMG de macOS solo se construye en un Mac con Apple
Silicon.

Ningún instalador incrusta el backend: construyen el entorno Python desde PyPI
en la máquina del usuario (Windows al instalar, con PyTorch CPU y el paquete CUDA
como opción para quien tenga GPU NVIDIA; macOS en el primer arranque). Para
Gemma en Mac sigue la [guía de modelos](modelos.md).

## Repetir solo el empaquetado de Windows

```powershell
pnpm run dist:win:installer
```

Este comando regenera `dist/windows-release/` y `.installer-build/`. No ejecuta
PyInstaller ni publica nada. Empaqueta lo que haya en `out/`, así que si cambiaste
código de la app ejecuta antes `pnpm run build`, o usa directamente
`pnpm run dist:win`.

## Comprobación manual

1. En Windows, descomprime el `.zip` y ejecuta el EXE. En macOS, instala el DMG
   de Apple Silicon.
2. Comprueba la instalación del backend, el progreso y el reintento tras una
   interrupción. Toda la instalación requiere Internet.
3. Confirma **Backend Python conectado** y `ollama show gemma4`.
4. Analiza un video corto, revisa los cortes, guarda y exporta un MP4 con audio.
5. Prueba en una cuenta sin el repositorio ni la `.venv` de desarrollo. Borra
   antes `%LOCALAPPDATA%\CREAcut\runtime` para comprobar la instalación limpia.
6. Si el equipo tiene GPU NVIDIA, comprueba también el paquete CUDA que ofrece
   el asistente; que falle no debe interrumpir la instalación.

## Publicar en GitHub

1. Revisa los cambios, crea tu commit y súbelo al repositorio.
2. Abre **Releases → Draft a new release**, selecciona el commit y usa el tag
   `v0.2.0-beta.1`, el título **CREACUT Beta 0.2** y **Set as a pre-release**.
3. Adjunta el archivo enumerado en
   `dist/windows-release/ARCHIVOS-PARA-PUBLICAR.txt`: el `.zip` de Windows.
   Conserva exactamente su nombre y usa el de la misma construcción.
4. Adjunta los DMG comprobados, verificando también su tamaño antes de subirlos.
5. Publica, comprueba [Downloads](../README.md#downloads) y la descarga del backend.
6. Retira los avisos de publicación solo para los archivos disponibles.

El botón de Windows descarga un único `.zip` con el instalador dentro. Los
archivos se adjuntan a la release, no al commit.

El manifiesto del backend se genera con la versión de `electron-editor/package.json`.
Al cambiar de versión, actualiza el tag, los nombres de instaladores, el bridge y
los enlaces juntos. El motor Python mantiene su versión de paquete independiente.

## Texto sugerido

> CREACUT Beta 0.2 para Windows y macOS. Importa un video y un guion, revisa
> las tomas propuestas y exporta a MP4. En Windows, descarga el `.zip` y abre el
> instalador: prepara Python, el backend, Whisper y Gemma 4. En macOS, la primera
> vez que abres la app prepara el entorno y Whisper; consulta su guía para Gemma. Requiere
> Internet durante la instalación y espacio adicional. Esta versión es beta.
