# Galería de proyectos de CREAcut Beta

La pantalla de bienvenida muestra los proyectos recientes como una pila de
tarjetas grandes. Cada tarjeta permite continuar un trabajo anterior sin buscar
manualmente el archivo `.creacut.json`.

## Qué ve la persona

- Nombre y ubicación del proyecto.
- Fecha relativa de la última apertura.
- Imágenes recientes del proyecto cuando están disponibles.
- Un botón para abrirlo.
- Un mensaje junto a la tarjeta si esa apertura falla.

Si todavía no hay proyectos recientes, la bienvenida muestra únicamente las
acciones para crear, abrir o procesar un lote.

## Estructura actual

```text
src/renderer/src/
├── views/WelcomeView.tsx
├── components/welcome/
│   ├── WelcomeHero.tsx
│   ├── CreaSculpture.tsx
│   ├── ProjectsGallery.tsx
│   ├── ProjectGalleryTile.tsx
│   ├── WorkflowSection.tsx
│   └── project-portfolio.css
├── hooks/
│   ├── useSmoothScroller.ts
│   └── useProjectStack.ts
├── services/
│   ├── smooth-scroll.ts
│   ├── project-stack-motion.ts
│   └── gallery-layout.ts
└── format.ts
```

`WelcomeView` compone las secciones. `ProjectsGallery` recibe la lista y crea
una tarjeta por proyecto. `ProjectGalleryTile` solo dibuja una tarjeta y envía
la ruta cuando se pulsa **Abrir**.

## De dónde salen los proyectos

El proceso principal conserva hasta diez proyectos recientes en
`recent-projects.json`, dentro de la carpeta de datos de la aplicación.
`recent-project-previews.ts` busca imágenes válidas cerca de cada proyecto para
mostrarlas sin modificar el archivo original.

El renderer recibe datos ya preparados. No recorre el disco ni abre archivos
por su cuenta.

## Animación de tarjetas apiladas

En ventanas grandes, las tarjetas anteriores quedan fijadas y se reducen
suavemente mientras aparece la siguiente. Lo hace el navegador, sin trabajo por
fotograma:

- `project-stack-motion.ts` calcula, a partir de las medidas de la pila, dónde
  se fija cada tarjeta, en qué tramo del scroll y cuánto se encoge.
- `useProjectStack` mide, escribe esos valores como variables CSS en cada
  ranura y pone la clase `is-stacked`. Vuelve a medir al cambiar el tamaño de la
  ventana o de las tarjetas.
- En `project-portfolio.css`, cada ranura se alarga como una pista y su tarjeta
  queda `position: sticky`; la escala es una animación ligada al scroll del
  documento (`animation-timeline: scroll(root)`).

El desplazamiento suave de la bienvenida lo da Lenis (`smooth-scroll.ts`), que
anima el scroll nativo y por eso no interfiere con `sticky`.

La animación se desactiva cuando:

- la ventana es pequeña;
- no hay altura suficiente;
- el sistema solicita reducir el movimiento;
- hay menos de dos tarjetas.

En esos casos las tarjetas se muestran una debajo de otra y siguen siendo
completamente utilizables.

## Accesibilidad

- El control para abrir es un botón real y funciona con teclado.
- Al navegar con Tab, la tarjeta enfocada se revela antes de activar el botón.
- Un clic no desplaza la tarjeta debajo del puntero.
- La reducción de movimiento del sistema elimina el apilado animado.
- Los mensajes de error aparecen junto al proyecto que falló.

## Estilos

Los estilos actuales están en `project-portfolio.css`. `styles.css` conserva
solo las reglas generales de la bienvenida y del desplazamiento suave. Las clases de la
galería horizontal anterior se retiraron porque ya no tenían elementos que las
utilizaran.

## Comprobación manual

1. Abre CREAcut Beta con varios proyectos recientes.
2. Desplázate hasta **Proyectos** y confirma que las tarjetas se apilan.
3. Abre una tarjeta y verifica que carga el proyecto correcto.
4. Regresa a Inicio y comprueba que la galería reaparece.
5. Navega con Tab y abre un proyecto con Enter.
6. Reduce el tamaño de la ventana; las tarjetas deben pasar al flujo normal.
7. Activa la reducción de movimiento del sistema y confirma que no se fijan.
8. Prueba una ruta inexistente y verifica que el error aparezca en su tarjeta.

Estas comprobaciones son manuales porque dependen del tamaño de la ventana, la
configuración del sistema y proyectos reales.
