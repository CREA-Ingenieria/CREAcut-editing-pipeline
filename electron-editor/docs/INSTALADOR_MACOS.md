# Instalar CREACUT en macOS

[← Inicio](../../README.md) · [Downloads](../../README.md#downloads) · [Documentación](../../docs/README.md)

## Descargar

**Beta 0.2** · CREAcut Beta para macOS requiere un Mac con chip Apple (M1 o
posterior).

| Equipo | Descarga directa |
|---|---|
| Apple Silicon | [↓ CREAcut-Beta-0.2-arm64.dmg](https://github.com/CREA-Ingenieria/CREAcut-editing-pipeline/releases/download/v0.2.0-beta.1/CREAcut-Beta-0.2-arm64.dmg) |

**Pendiente de publicación:** el DMG debe construirse y comprobarse en un Mac
con Apple Silicon antes de publicarlo.

## Instalar

1. Abre el DMG y arrastra **CREAcut Beta** a **Aplicaciones**.
2. Abre CREAcut con clic derecho → **Abrir** (la beta aún no está firmada). En
   macOS 15 o posterior ese clic ya no basta: ábrela una vez, ve a **Ajustes del
   Sistema → Privacidad y seguridad** y pulsa **Abrir igualmente**.
3. La primera vez aparece **Preparando CREAcut para tu Mac**. CREAcut descarga
   Python 3.12, PyTorch, las dependencias (incluido FFmpeg) y Whisper
   `large-v3` y `medium`: unos 5 GB. Mantén la conexión a Internet; puedes
   seguir con otra cosa mientras tanto.
4. Al terminar se abre la bienvenida. Las siguientes veces entra directo.

Si la preparación falla (sin conexión o sin espacio), pulsa **Reintentar**. Si
cierras la app a mitad de camino, la preparación vuelve a empezar al abrirla.

| Qué | Dónde |
|---|---|
| Entorno Python | `~/Library/Application Support/CREAcut/runtime/` |
| Modelos de Whisper | `~/.cache/whisper/` |
| Registro de la preparación y de la comprobación de cada arranque | `~/Library/Logs/CREAcut/backend-setup.log` |

Para repetir la preparación desde cero, cierra CREAcut y borra la carpeta
`runtime/`.

### Gemma 4 (opcional)

Las listas animadas usan Gemma 4 mediante Ollama. Instala y abre
[Ollama para macOS](https://ollama.com/download/mac) y descarga el modelo:

```bash
ollama pull gemma4
ollama show gemma4
```

Ollama requiere macOS 14 o posterior y admite Apple Silicon e Intel.
Consulta sus [requisitos oficiales](https://docs.ollama.com/macos).

[Primer proyecto →](../../docs/GUIA_USUARIO.md) · [Modelos y cachés →](../../docs/modelos.md)

## Problemas frecuentes

- **La app no abre:** comprueba que tu Mac tenga chip Apple. La beta todavía no está firmada
  ni notarizada; si macOS la bloquea, verifica su origen y revisa
  **Ajustes del Sistema → Privacidad y seguridad**.
- **La preparación no avanza:** revisa `~/Library/Logs/CREAcut/backend-setup.log`.
  Si `uv` no se puede ejecutar, abre **Ajustes del Sistema → Privacidad y
  seguridad** y permite CREAcut.
- **Gemma no responde:** abre Ollama y comprueba `ollama show gemma4`.
- **Whisper usa CPU:** es el comportamiento actual de CREAcut en macOS; el selector
  todavía no activa Metal/MPS.

## Actualizar o desinstalar

Para actualizar, cierra CREAcut y reemplázala en Aplicaciones con la nueva copia.
Para desinstalar, mueve **CREAcut Beta.app** a la Papelera. Los videos, proyectos,
modelos y Ollama se conservan.

Al actualizar, CREAcut conserva el entorno si la versión no cambió. Para liberar
espacio al desinstalar, borra también:

- `~/Library/Application Support/CREAcut/` (el entorno Python).
- `~/.cache/whisper/` (los modelos de Whisper, unos 4,5 GB), si ningún otro
  programa los usa.
- `~/.cache/uv/` (la caché de descargas de `uv`).

## Construir el DMG

En un Mac con Apple Silicon, desde `electron-editor`: `pnpm install` y
`pnpm run dist:mac`. Genera `dist/CREAcut-Beta-0.2-arm64.dmg`. No hace falta
`.venv` ni PyInstaller: el DMG lleva las fuentes de CREAcut y `uv`, y
`scripts/verify-bundle.mjs` hace fallar el empaquetado si se cuela FFmpeg o
cualquier binario de Python.

### Comprobación manual antes de publicar

- Después de arrastrar la app a Aplicaciones desde el DMG descargado,
  `xattr -l "/Applications/CREAcut Beta.app/Contents/Resources/backend-setup/uv"`
  muestra si `uv` conserva `com.apple.quarantine` y, aun así, la preparación
  lo puede ejecutar.
- Tras una primera preparación completa,
  `codesign --verify --deep "/Applications/CREAcut Beta.app"` sigue pasando:
  nada se escribió dentro del `.app` (los `.pyc` van a `runtime/pycache`).
- Cierra con Cmd+Q mientras se instala PyTorch y comprueba con
  `ps -ax | grep -E 'uv|python'` que no queda ningún `uv` ni `python` huérfano.
  Al volver a abrir, la preparación empieza de nuevo y termina bien.
- Anota cuánto dura **Abriendo CREAcut…** en un arranque en frío (Mac recién
  encendido) con el entorno ya preparado.

[Comprobación y publicación manual →](../../docs/publicacion.md)
