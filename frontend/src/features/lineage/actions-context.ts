import { createContext, useContext } from 'react'
import type { Direction } from './graph/graph-state'

export interface LineageActions {
  expand: (nodeId: string, direction: Direction) => void
  collapse: (nodeId: string, direction: Direction) => void
  toggleShowAll: (nodeId: string) => void
  selectColumn: (nodeId: string, column: string) => void
}

const noop: LineageActions = { expand: () => {}, collapse: () => {}, toggleShowAll: () => {}, selectColumn: () => {} }

/** Node components read their callbacks from context so node `data` stays serialisable and memo-friendly. */
export const LineageActionsContext = createContext<LineageActions>(noop)

export function useLineageActions(): LineageActions {
  return useContext(LineageActionsContext)
}
