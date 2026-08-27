import { createContext, useContext } from 'react'
import { useParams } from 'react-router'
import type { ScanDetail, SnapshotSummary } from '@/api/types'

export interface ScanContextValue {
  scanId: number
  scan: ScanDetail
  summary: SnapshotSummary
  connection: string
}

export const ScanContext = createContext<ScanContextValue | null>(null)

/** The current scan (only valid under `/s/:scanId`). Throws outside a scan route. */
export function useScanContext(): ScanContextValue {
  const ctx = useContext(ScanContext)
  if (!ctx) throw new Error('useScanContext must be used inside a /s/:scanId route')
  return ctx
}

export function useOptionalScan(): ScanContextValue | null {
  return useContext(ScanContext)
}

/** Scan id from the URL, if any (works even before the scan has loaded). */
export function useScanId(): number | null {
  const { scanId } = useParams()
  const n = Number(scanId)
  return scanId != null && Number.isFinite(n) ? n : null
}
