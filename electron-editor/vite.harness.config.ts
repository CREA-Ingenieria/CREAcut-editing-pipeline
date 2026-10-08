import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

/**
 * Servidor de desarrollo solo para el banco de pruebas visual del editor
 * (`src/renderer/harness.html`). No participa en `pnpm run build`, que sigue
 * usando `electron.vite.config.ts` e `index.html`.
 */
export default defineConfig({
  root: resolve('src/renderer'),
  resolve: {
    alias: {
      '@renderer': resolve('src/renderer/src'),
      '@shared': resolve('src/shared')
    }
  },
  plugins: [react(), tailwindcss()],
  server: { port: 5199, open: false }
})
