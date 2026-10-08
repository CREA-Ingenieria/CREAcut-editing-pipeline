/**
 * Reglas puras de la galería de proyectos de la pantalla de bienvenida.
 *
 * No depende de React ni del DOM: recibe la lista de proyectos
 * recientes y devuelve las tarjetas que hay que pintar. Mantenerlo aparte
 * permite razonar (y probar) la composición de la tira sin montar la interfaz.
 *
 * La galería apila tarjetas verticales, sin un número fijo de celdas: se pintan
 * tantas tarjetas como proyectos haya. El proceso principal ya limita los
 * recientes a diez.
 */
import type { RecentProject } from '../../../shared/contracts'

/** Número de variantes cromáticas de marca disponibles para las tarjetas. */
export const GALLERY_ACCENTS = 4

export interface GalleryTile {
  /** Clave estable para React. */
  key: string
  project: RecentProject
  /** Variante cromática de marca, en `[0, GALLERY_ACCENTS)`. */
  accent: number
}

/**
 * Elige una variante cromática determinista a partir de una semilla.
 *
 * Se usa la ruta del proyecto como semilla para que un mismo proyecto conserve
 * su color entre sesiones: una galería que cambia de color en cada arranque se
 * vuelve imposible de reconocer de un vistazo.
 */
export function tileAccent(seed: string): number {
  let hash = 0
  for (let index = 0; index < seed.length; index += 1) {
    hash = (Math.imul(hash, 31) + seed.charCodeAt(index)) | 0
  }
  return Math.abs(hash) % GALLERY_ACCENTS
}

/**
 * Convierte los proyectos recientes en las tarjetas de la tira, conservando el
 * orden en que llegan (del más reciente al más antiguo).
 */
export function buildGalleryTiles(projects: RecentProject[]): GalleryTile[] {
  return projects.map((project) => ({
    key: `project:${project.path}`,
    project,
    accent: tileAccent(project.path)
  }))
}

/**
 * Firma del contenido de la tira.
 *
 * El hook de animación vuelve a medir cuando cambia esta cadena. Sirve para no
 * rehacer el apilado en cada render de React, sino solo cuando las
 * tarjetas realmente cambian.
 */
export function galleryTilesSignature(tiles: GalleryTile[]): string {
  return tiles.map((tile) => tile.key).join('|')
}
