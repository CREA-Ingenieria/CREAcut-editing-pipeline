import { Moon, Sun } from 'lucide-react'
import type { ThemeMode } from '../types/editor'
import { Button } from './ui/button'

interface ThemeButtonProps {
  theme: ThemeMode
  onToggle: () => void
}

export function ThemeButton({ theme, onToggle }: ThemeButtonProps): React.JSX.Element {
  return (
    <Button variant="icon" size="icon" title="Cambiar tema" onClick={onToggle}>
      {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
    </Button>
  )
}
