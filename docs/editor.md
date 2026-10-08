# Editor legado PySide6 de CREAcut Beta

> **Estado:** esta es la interfaz anterior. El editor principal actual está en
> `electron-editor/` y se documenta en
> [`electron-editor/README.md`](../electron-editor/README.md). PySide6 se
> conserva para compatibilidad, demostraciones y diagnóstico del Core Python.

El editor PySide6 abre los proyectos editables generados por el pipeline y permite
inspeccionar la edición automática antes del render final. Es una aplicación de
escritorio en PySide6; no inicia un servidor web.

## Instalación

La interfaz es una dependencia opcional para que el pipeline siga funcionando
en entornos sin escritorio:

```bash
pip install -e ".[ui]"
```

## Crear un proyecto editable

```bash
creacut clase.mp4 \
  --script guion.md \
  --project-only \
  --project-output clase.creacut.json
```

Este paso ejecuta transcripción y alineación, pero no renderiza el MP4 final.

## Probar el editor sin tener un video

El repositorio incluye una demostración completamente local. Genera un MP4 de
12 segundos, un guion y un proyecto editable con dos tomas alternativas. No
ejecuta Whisper, no necesita conexión a Internet y tampoco requiere que el
comando `ffmpeg` esté instalado en el `PATH`:

```bash
python scripts/create_editor_demo.py --output-dir demo_editor
python -m creacut.ui demo_editor/creacut-demo.creacut.json
```

Si vuelves a ejecutar el primer comando, un demo intacto se valida y reutiliza.
Si modificaste el proyecto o hay una colisión, el generador se detiene sin
sobrescribir nada. Usa `--force` únicamente si quieres restablecer sus tres
archivos al estado inicial.

En **Original** se ven, en orden, `TOMA A`, `TOMA B` y `FINAL`. En **Edición
propuesta**, CREAcut conserva inicialmente `TOMA B` y `FINAL`. Para comprobar la
edición manual, selecciona la primera oración, elige `Toma A` y pulsa **Usar
esta toma**; el preview debe cambiar inmediatamente a `TOMA A` y `FINAL`.

Esta demostración prueba la apertura, reproducción, preview de cortes, selección
de tomas, línea de tiempo fuente y persistencia del proyecto. No prueba Whisper
ni la alineación sobre una grabación real.

## Abrir el editor

```bash
python -m creacut.ui clase.creacut.json
```

Si instalaste los comandos del paquete, `creacut-editor clase.creacut.json` es
equivalente.

Sin una ruta inicial, usa **Archivo > Abrir proyecto**.

## Funciones disponibles

- Reproducir y recorrer el video original.
- Ver una línea de tiempo de **todo el video fuente** desde `00:00` hasta su
  duración: el material descartado permanece visible y atenuado.
- Ver regla temporal, playhead sincronizado, filmstrip de miniaturas y forma de
  onda cuando el archivo contiene audio. Estos datos se generan en segundo
  plano y se almacenan como caché local en `.creacut-cache`; nunca modifican el
  MP4 ni el JSON del proyecto.
- Hacer clic en la línea de tiempo para mover el playhead. Si se está viendo la
  edición propuesta y se pulsa un descarte, el editor vuelve temporalmente al
  video fuente para poder auditarlo.
- Seleccionar una región y usar **Conservar región**, **Descartar región** o
  **Restaurar automático**. Un borde se puede arrastrar para mover un corte y
  **Dividir en playhead** crea una región independiente. Los controles `+` y
  `−`, o `Ctrl` + rueda del ratón, ajustan el zoom horizontal.
- Cambiar a **Edición propuesta (cortes rápidos)** para revisar únicamente los
  rangos actualmente marcados para conservar. La línea visual sigue usando el
  reloj del video fuente, por lo que los saltos muestran exactamente qué se
  omitió.
- Saltar al corte anterior o siguiente.
- Consultar cada oración, su rango, score, texto transcrito, toma recomendada,
  alternativas y diagnóstico de selección.
- Sustituir la toma activa por cualquiera de las alternativas detectadas y
  restaurar después la recomendación automática de CREAcut.
- Ubicar manualmente el video fuente si el proyecto fue movido. Esta ubicación
  es temporal y no altera la procedencia guardada en el proyecto.
- Guardar o guardar como un proyecto validado.
- Renderizar el proyecto aprobado sin volver a ejecutar Whisper ni alineación:

  ```bash
  creacut render-project clase.creacut.json --output clase-final.mp4 --verbose
  ```

Seleccionar una fila de la tabla no cambia el proyecto. Usa **Usar esta toma**
o haz doble clic para aplicarla. El cambio actualiza inmediatamente los rangos
derivados y el preview; una toma que produzca una secuencia cronológicamente
inválida se rechaza sin modificar el proyecto.

Las decisiones de timeline se guardan como una extensión versionada del
proyecto. Así, los JSON existentes siguen siendo válidos y continúan usando
exactamente el compilador histórico si nunca se hace una edición de timeline.

## Alcance del preview actual

La edición propuesta se reproduce directamente desde el video original y salta
entre rangos; no genera un proxy ni un MP4 temporal. Por eso permite revisar los
cortes rápidamente, pero todavía no reproduce crossfades, chroma, overlays,
bookends, normalización ni offsets de audio. Esos elementos pertenecen al
render final.

Los cortes manuales son no destructivos: se guardan como rangos `keep/discard`
en coordenadas del video fuente. El render usa esos rangos exactamente y no
vuelve a aplicar padding o uniones automáticas sobre un corte manual.

El render desde proyecto vuelve a generar los overlays que puedan derivarse del
guion y aplica chroma, transiciones, bookends y normalización según la
configuración guardada. Los offsets de audio permanecen como metadatos de
proyecto; todavía no se aplican al preview ni al render.

La precisión de seek depende del codec y del backend multimedia disponible en
el sistema. Si el medio no admite seek, el video original puede seguir siendo
reproducible, pero el modo de edición propuesta queda deshabilitado.
