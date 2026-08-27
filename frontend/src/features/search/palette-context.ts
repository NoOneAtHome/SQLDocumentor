import { createContext, useContext } from 'react'

export interface PaletteContextValue {
  isOpen: boolean
  open: (initialQuery?: string) => void
  close: () => void
}

export const PaletteContext = createContext<PaletteContextValue | null>(null)

export function useCommandPalette(): PaletteContextValue {
  const ctx = useContext(PaletteContext)
  if (!ctx) throw new Error('useCommandPalette must be used within CommandPaletteProvider')
  return ctx
}
