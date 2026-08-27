const DASH = '—'

function trimZero(s: string): string {
  return s.replace(/\.0$/, '')
}

/** 999 → "999", 1234 → "1.2k", 1_200_000 → "1.2M", 2.5e9 → "2.5B". */
export function formatCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return DASH
  const abs = Math.abs(n)
  if (abs < 1000) return String(Math.round(n))
  const units: Array<[number, string]> = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'k'],
  ]
  for (const [value, suffix] of units) {
    if (abs >= value) return trimZero((n / value).toFixed(1)) + suffix
  }
  return String(n)
}

export function formatRows(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return DASH
  if (n === 1) return '1 row'
  return `${formatCompact(n)} rows`
}

/** Kilobytes → human size ("512 KB", "1.5 MB", "1.2 GB"). */
export function formatKb(kb: number | null | undefined): string {
  if (kb == null || Number.isNaN(kb)) return DASH
  const K = 1024
  if (kb < K) return `${Math.round(kb)} KB`
  if (kb < K * K) return `${trimZero((kb / K).toFixed(1))} MB`
  if (kb < K * K * K) return `${trimZero((kb / (K * K)).toFixed(1))} GB`
  return `${trimZero((kb / (K * K * K)).toFixed(1))} TB`
}

/** Microseconds → "850 µs" / "12.5 ms" / "1.20 s" / "2m 05s". */
export function formatMicros(us: number | null | undefined): string {
  if (us == null || Number.isNaN(us)) return DASH
  if (us < 1_000) return `${Math.round(us)} µs`
  if (us < 1_000_000) return `${trimZero((us / 1_000).toFixed(1))} ms`
  if (us < 60_000_000) return `${(us / 1_000_000).toFixed(2)} s`
  const totalSeconds = Math.round(us / 1_000_000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

/** Milliseconds → same scale as formatMicros. */
export function formatMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return DASH
  return formatMicros(ms * 1_000)
}

/** Coarser duration for scans ("450 ms", "8.2 s", "1m 12s"). */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return DASH
  if (ms < 1_000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1_000).toFixed(1)} s`
  const totalSeconds = Math.round(ms / 1_000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return DASH
  return n.toLocaleString('en-US')
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio == null || Number.isNaN(ratio)) return DASH
  return `${Math.round(ratio * 100)}%`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return d.toLocaleDateString('en-US', { dateStyle: 'medium' })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return d.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

/** "just now", "3 min ago", "3 h ago", "5 d ago", then an absolute date. */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  const seconds = Math.max(0, Math.round((now.getTime() - d.getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} d ago`
  return formatDate(iso)
}

export function pluralize(n: number, singular: string, plural = `${singular}s`): string {
  return `${formatNumber(n)} ${n === 1 ? singular : plural}`
}
