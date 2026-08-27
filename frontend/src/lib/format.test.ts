import { describe, expect, it } from 'vitest'
import {
  formatCompact,
  formatDurationMs,
  formatKb,
  formatMicros,
  formatMs,
  formatNumber,
  formatPercent,
  formatRelative,
  formatRows,
} from './format'

describe('formatCompact', () => {
  it('returns a dash for missing values', () => {
    expect(formatCompact(null)).toBe('—')
    expect(formatCompact(undefined)).toBe('—')
  })
  it('keeps small numbers verbatim', () => {
    expect(formatCompact(0)).toBe('0')
    expect(formatCompact(999)).toBe('999')
  })
  it('abbreviates thousands, millions and billions with one decimal', () => {
    expect(formatCompact(1_234)).toBe('1.2k')
    expect(formatCompact(4_300)).toBe('4.3k')
    expect(formatCompact(1_200_000)).toBe('1.2M')
    expect(formatCompact(31_465)).toBe('31.5k')
    expect(formatCompact(2_500_000_000)).toBe('2.5B')
  })
  it('drops a trailing .0', () => {
    expect(formatCompact(1_000)).toBe('1k')
    expect(formatCompact(2_000_000)).toBe('2M')
  })
})

describe('formatRows', () => {
  it('pluralises and abbreviates', () => {
    expect(formatRows(1)).toBe('1 row')
    expect(formatRows(0)).toBe('0 rows')
    expect(formatRows(1_200_000)).toBe('1.2M rows')
    expect(formatRows(null)).toBe('—')
  })
})

describe('formatKb', () => {
  it('scales KB into MB / GB / TB', () => {
    expect(formatKb(0)).toBe('0 KB')
    expect(formatKb(512)).toBe('512 KB')
    expect(formatKb(1_536)).toBe('1.5 MB')
    expect(formatKb(1_258_291)).toBe('1.2 GB')
    expect(formatKb(1_073_741_824 * 1.5)).toBe('1.5 TB')
    expect(formatKb(null)).toBe('—')
  })
})

describe('formatMicros / formatMs', () => {
  it('shows microseconds below 1 ms', () => {
    expect(formatMicros(850)).toBe('850 µs')
    expect(formatMs(0.5)).toBe('500 µs')
  })
  it('shows milliseconds with one decimal below 1 s', () => {
    expect(formatMicros(12_500)).toBe('12.5 ms')
    expect(formatMs(12.5)).toBe('12.5 ms')
    expect(formatMs(999)).toBe('999 ms')
  })
  it('shows seconds with two decimals below a minute', () => {
    expect(formatMicros(1_200_000)).toBe('1.20 s')
    expect(formatMs(1_200)).toBe('1.20 s')
  })
  it('shows minutes and seconds beyond a minute', () => {
    expect(formatMs(125_000)).toBe('2m 05s')
    expect(formatMicros(60_000_000)).toBe('1m 00s')
  })
  it('handles missing values', () => {
    expect(formatMs(null)).toBe('—')
    expect(formatMicros(undefined)).toBe('—')
  })
})

describe('formatDurationMs', () => {
  it('formats scan durations', () => {
    expect(formatDurationMs(8_200)).toBe('8.2 s')
    expect(formatDurationMs(72_000)).toBe('1m 12s')
    expect(formatDurationMs(450)).toBe('450 ms')
    expect(formatDurationMs(null)).toBe('—')
  })
})

describe('formatNumber / formatPercent', () => {
  it('adds thousands separators', () => {
    expect(formatNumber(1_234_567)).toBe('1,234,567')
    expect(formatNumber(null)).toBe('—')
  })
  it('formats ratios as percentages', () => {
    expect(formatPercent(0.874)).toBe('87%')
    expect(formatPercent(1)).toBe('100%')
    expect(formatPercent(null)).toBe('—')
  })
})

describe('formatRelative', () => {
  const now = new Date('2026-08-26T12:00:00Z')
  it('describes recent instants', () => {
    expect(formatRelative('2026-08-26T11:59:50Z', now)).toBe('just now')
    expect(formatRelative('2026-08-26T11:57:00Z', now)).toBe('3 min ago')
    expect(formatRelative('2026-08-26T09:00:00Z', now)).toBe('3 h ago')
    expect(formatRelative('2026-08-21T12:00:00Z', now)).toBe('5 d ago')
  })
  it('falls back to a date beyond a month', () => {
    expect(formatRelative('2026-05-01T12:00:00Z', now)).toMatch(/2026/)
  })
  it('handles missing values', () => {
    expect(formatRelative(null, now)).toBe('—')
  })
})
