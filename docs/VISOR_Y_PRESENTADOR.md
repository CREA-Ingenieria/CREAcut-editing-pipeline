# Visor y presentador de CREAcut Beta

> Documento técnico de la beta `0.2.0-beta.1`. Los pasos finales son
> comprobaciones manuales, no una certificación de funcionamiento.

El contenedor `stageRef` (`data-video-canvas`) de `VideoPreview.tsx` es el
lienzo completo y la referencia de posición. `SlidePresenterHandle.tsx` es
hijo directo suyo. Ambos están dentro del área visible `data-video-viewer`,
que también contiene el separador horizontal superpuesto.

Las posiciones X/Y y las dimensiones ancho/alto se guardan como fracciones
del lienzo completo. CSS las convierte en porcentajes; mover el visor o
cambiar el ancho del layout no escribe cambios en la geometría del proyecto.
La diapositiva y el presentador se escalan juntos, conservando la proporción
del vídeo obtenida de sus metadatos (16:9 provisional mientras carga).

La altura mínima, predeterminada y máxima del panel es el alto del lienzo completo
(ancho disponible / proporción del vídeo), más 50 px de pestañas y 58 px de
controles. CSS calcula esta altura directamente con `aspectRatio`, sin
`ResizeObserver`, estado de altura en el padre ni reparto `flex-1` con la
línea de tiempo. El separador no reserva espacio dentro del lienzo: se superpone
a sus últimos 12 px. No permite reducir el área visible ni añadir espacio
vacío por debajo del vídeo. Como ambos límites coinciden, el separador es
visual y ya no tiene arrastre ni botón de restaurar. El resultado corresponde
a la primera captura de referencia (vídeo completo), no a la segunda recortada.
La altura se adapta al ancho disponible sin estrechar, achatar ni recolocar
independientemente al presentador.
La antigua altura fija guardada en localStorage ya no se utiliza; al abrir
el editor se muestra el lienzo completo por defecto.

El visor establece un contexto de capas aislado: vídeo/fondo (z-index 1–3),
presentador (4), separador (6). El separador es opaco y cubre la porción del
presentador que lo cruza. El borde del visor recorta lo que sale del lienzo
sin desplazar ni reducir al presentador. El render MP4 aplica el mismo criterio
de recorte para las coordenadas guardadas, sin incluir los controles del editor.

## Comprobación manual

1. Reinicia Electron con `pnpm dev` desde `electron-editor` y abre un proyecto.
2. En **Inspector → Diapositivas**, agrega o activa una diapositiva en la pista.
   Arrastra su bloque para moverlo y sus extremos para cambiar inicio/fin.
3. Solicita el fotograma de previsualización dentro de ese intervalo para
   mostrar la diapositiva y el presentador editable.
4. Comprueba que el visor abre ajustado al vídeo, sin espacio vacío inferior.
   Intenta subir y bajar el separador: no debe cambiar esa altura. Prueba también con
   un vídeo vertical o 4:3 para comprobar que usa su proporción real.
5. Coloca el presentador abajo a la derecha; anota X/Y/ancho/alto. Intentar
   arrastrar el separador no debe ocultar parte de la diapositiva ni cambiar
   el tamaño o posición del presentador. Los porcentajes deben permanecer iguales.
6. Cambia el ancho de la ventana y desplaza verticalmente el panel central.
   Verifica que visor y presentador se desplacen y escalen juntos, y que el
   alto se actualice al nuevo ancho manteniendo el vídeo completo.
7. Pon Y en 80 % y altura en 40 %. El presentador debe cruzar el borde inferior
   y quedar tapado por el separador, sin saltar hacia arriba ni encogerse.
8. Guarda, cierra y reabre. Verifica que se conserven los porcentajes, incluidos
   los que hacen que la caja sobresalga. Exporta manualmente si quieres comprobar
   que el MP4 recorta el excedente en vez de recolocar al presentador.

Estas comprobaciones visuales no se ejecutaron automáticamente.

## Encuadre fijo y primer fotograma de exportación

La vista de efectos y el MP4 ajustan el mismo rectángulo de cámara guardado
(`crop_x`, `crop_y`, `crop_width`, `crop_height`) dentro de la caja del
presentador. Los márgenes transparentes se conservan: el contorno del chroma
de cada fotograma no vuelve a calcular la escala ni el anclaje. Los gestos
naturales del video continúan, pero no deben provocar zooms o desplazamientos
añadidos por el compositor. X/Y/ancho/alto siguen siendo los que guardaste.

Si hay una diapositiva activa al inicio de la edición exportada, aparece
completa desde el primer fotograma. Si no la hay, aparece el fondo configurado
del pipeline. Al entrar en una diapositiva no se mezcla el fotograma del
pipeline, que contenía otra copia del presentador en su posición original.
El fundido entre fondos se conserva para diapositivas consecutivas.

Comprobación manual: reinicia el editor, solicita de nuevo la vista de efectos,
ajusta y guarda la caja del presentador. Exporta una secuencia con gestos y una
diapositiva activa desde el inicio; comprueba que no aparezca blanco antes de
ella y que la capa no cambie de escala ni de anclaje. Repite con un inicio sin
diapositiva para comprobar el fondo configurado. No se ha ejecutado esta
exportación de prueba automáticamente.

## Dónde ajustarlo manualmente

- `electron-editor/src/renderer/src/components/VideoPreview.tsx`:
  `aspectRatio` obtiene la proporción del vídeo. El div `data-video-canvas`
  usa `style={{ aspectRatio }}` y `w-full`: su altura es ancho / proporción.
  Para diagnosticar un vídeo 16:9, puedes probar temporalmente
  `style={{ aspectRatio: '16 / 9' }}` en ese div. No lo dejes fijo para vídeos
  verticales o 4:3. El div `data-video-viewer` debe conservar `shrink-0`,
  sin `flex-1` ni altura fija. El separador está en el bloque `role="separator"`:
  `bottom-0` lo ancla abajo, `h-3` define una franja de 12 px y `z-[6]` lo
  mantiene por encima del presentador.
- `electron-editor/src/renderer/src/views/EditorView.tsx`: el contenedor
  inmediato de `VideoPreview` debe conservar `shrink-0`, sin `height` en
  píxeles ni `h-full` en el componente. El panel central permite scroll:
  la línea de tiempo no debe comprimir el visor para caber en la ventana.
- `electron-editor/src/renderer/src/components/SlidePresenterHandle.tsx`:
  las dimensiones y posiciones porcentuales se refieren a `stageRef`.
  No cambies esos porcentajes para compensar un problema de altura del visor.

## Abrir los cambios correctos

Modificar `src` no actualiza una aplicación instalada ni un `out` compilado
anteriormente. Desde PowerShell, en la raíz del repositorio, ejecuta **una** de
estas rutas:

Desarrollo (lee el código actual):

```powershell
Set-Location '.\electron-editor'
pnpm dev
```

Versión compilada local:

```powershell
Set-Location '.\electron-editor'
pnpm build
pnpm preview
```

No edites los archivos generados dentro de `out`: se reemplazan al compilar.
El acceso directo de una instalación anterior no se actualiza con estos
comandos. Para generar otro instalador de Windows, usa `pnpm run dist:win`;
instálalo manualmente después de guardar y cerrar la aplicación anterior.
