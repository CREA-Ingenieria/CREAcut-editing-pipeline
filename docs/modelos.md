# Whisper y Gemma 4

[← Documentación](README.md) · [Downloads](../README.md#downloads)

## Modelos de la beta 0.2

| Modelo | Identificador | Uso |
|---|---|---|
| Whisper | `large-v3` | Transcribir la grabación |
| Whisper | `medium` | Alternativa en CUDA cuando falta VRAM; preparada por el EXE |
| Gemma 4 en Ollama | `gemma4` | Extraer listas para los overlays |

Los modelos principales están definidos en [config.py](../creacut/config.py);
la alternativa de Whisper sigue la regla de [transcripción](../creacut/transcribe.py).
`gemma4` se resuelve como `gemma4:latest`: conserva el nombre del código, pero
no fija una revisión inmutable de los pesos.

## Preparación por sistema

| Sistema | Whisper | Gemma 4 y Ollama |
|---|---|---|
| Windows | El EXE descarga `large-v3` y `medium` al instalar | Prepara `gemma4` e instala Ollama si falta |
| macOS | Descarga `large-v3` en la primera transcripción | Instala y abre Ollama; ejecuta `ollama pull gemma4` |

Descargar el EXE o DMG en el navegador solo guarda el instalador. Los modelos
requieren Internet y varios GB adicionales. Después se reutilizan las cachés.

[Instalación Windows →](../electron-editor/docs/INSTALADOR_WINDOWS.md) ·
[Instalación macOS →](../electron-editor/docs/INSTALADOR_MACOS.md)

## Cachés y reintentos

| Archivo | Windows | macOS |
|---|---|---|
| Whisper | `%USERPROFILE%\.cache\whisper` | `~/.cache/whisper` |
| Modelos de Ollama | `%USERPROFILE%\.ollama\models` | `~/.ollama/models` |

Whisper respeta `XDG_CACHE_HOME` y Ollama permite cambiar su almacén con
`OLLAMA_MODELS`. Usa la misma cuenta al preparar los modelos y abrir CREAcut.

En Windows, el asistente verifica Whisper mediante SHA-256, reutiliza archivos
completos y permite reintentar. Repite el instalador si la preparación se interrumpe.
Su servidor Ollama debe ser local; el registro está en
`%LOCALAPPDATA%\CREAcut\logs\ollama-setup.log`.

En macOS, vuelve a iniciar la transcripción si falla la descarga de Whisper.
Para descargar o comprobar Gemma en cualquiera de los sistemas, con Ollama abierto:

```bash
ollama pull gemma4
ollama show gemma4
```

El asistente de Windows reutiliza Gemma si ya está instalado; ejecutar `ollama pull`
puede actualizar el contenido de la etiqueta. Whisper usa CPU en macOS actualmente;
en Windows selecciona CUDA cuando está disponible, sin cambiar silenciosamente
a CPU tras agotar la VRAM.

## Configuración personalizada

El EXE prepara los valores predeterminados del código. Si eliges otro modelo en
un YAML, tendrás que descargarlo también. El proveedor de listas sigue siendo
`auto`: intenta Ollama, Claude si está configurado y, finalmente, reglas.
Consulta [Configuración](configuration.md) para elegir el proveedor.

## Referencias

[Gemma 4](https://ollama.com/library/gemma4) ·
[Ollama Windows](https://docs.ollama.com/windows) ·
[Ollama macOS](https://docs.ollama.com/macos) ·
[Asistente del EXE](../electron-editor/python/setup_models.py)
