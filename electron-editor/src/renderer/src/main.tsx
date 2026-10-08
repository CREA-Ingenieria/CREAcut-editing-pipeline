import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import { App } from './App'
import { TooltipProvider } from './components/ui/tooltip'
import { BackendGate } from './views/BackendGate'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* `delayDuration` corto: en una barra de iconos, esperar 700ms a saber que
        hace cada uno convierte la ayuda en un estorbo. */}
    <TooltipProvider delayDuration={280} skipDelayDuration={400}>
      <BackendGate>
        <App />
      </BackendGate>
    </TooltipProvider>
  </React.StrictMode>
)
