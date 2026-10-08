import type { CreacutApi } from '../../shared/contracts'

declare global {
  interface Window {
    creacut: CreacutApi
  }
}

export {}
