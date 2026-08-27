import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** Modifier-key glyph for shortcut hints. */
export const modKey = isMac ? '⌘' : 'Ctrl'

export function qualifiedName(ref: { schema: string; name: string }): string {
  return `${ref.schema}.${ref.name}`
}

/** Extract a human-readable message from an API error body, a fetch failure, or an Error. */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (!err) return fallback
  if (typeof err === 'string') return err
  if (err instanceof Error) return err.message || fallback
  if (typeof err === 'object' && 'detail' in err) {
    const detail = (err as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join('; ')
    }
  }
  return fallback
}

export function isNotFound(err: unknown): boolean {
  return typeof err === 'object' && !!err && 'status' in err && (err as { status: unknown }).status === 404
}

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n))
}

export function uniq<T>(items: Iterable<T>): T[] {
  return [...new Set(items)]
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, ms: number) {
  let t: ReturnType<typeof setTimeout> | null = null
  const debounced = (...args: A) => {
    if (t) clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
  debounced.cancel = () => {
    if (t) clearTimeout(t)
    t = null
  }
  return debounced
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
