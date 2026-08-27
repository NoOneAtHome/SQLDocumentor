import { useEffect } from 'react'
import { useTheme } from '@/lib/theme'

export function isEditableTarget(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/** App-wide shortcuts (⌘K and ⌘B are handled by the palette and sidebar). */
export function useGlobalShortcuts({ onHelp }: { onHelp: () => void }) {
  const { toggle } = useTheme()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'd') {
        e.preventDefault()
        toggle()
        return
      }
      if (e.key === '?' && !isEditableTarget(e) && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        onHelp()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle, onHelp])
}
