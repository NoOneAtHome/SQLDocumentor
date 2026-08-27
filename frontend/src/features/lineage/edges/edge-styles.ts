import type { Confidence, EdgeKind } from '@/api/types'

export function edgeKindColor(kind: EdgeKind): string {
  switch (kind) {
    case 'fk':
      return 'var(--edge-fk)'
    case 'trigger':
      return 'var(--edge-trigger)'
    case 'parsed_read':
    case 'parsed_write':
    case 'parsed_exec':
      return 'var(--edge-parsed)'
    case 'synonym':
      return 'var(--edge-synonym)'
    default:
      return 'var(--edge-catalog)'
  }
}

export function confidenceColor(c: Confidence): string {
  return c === 'exact' ? 'var(--conf-exact)' : c === 'inferred' ? 'var(--conf-inferred)' : 'var(--conf-unresolved)'
}

export function confidenceDash(c: Confidence): string | undefined {
  return c === 'exact' ? undefined : c === 'inferred' ? '6 4' : '2 3'
}
