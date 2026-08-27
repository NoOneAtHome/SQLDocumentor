import type { ElkPort } from 'elkjs/lib/elk-api'

/** Object-level node card (spec: 240×64). */
export const OBJECT_NODE_WIDTH = 240
export const OBJECT_NODE_HEIGHT = 64

/** Column-level table node: header + one row per participating column (+ optional footer). */
export const COLUMN_NODE_WIDTH = 260
export const COLUMN_HEADER_H = 40
export const COLUMN_ROW_H = 24
export const COLUMN_FOOTER_H = 22

/** ELK port square size — its centre must sit exactly on the Handle centre. */
export const PORT_SIZE = 8

export type PortSide = 'in' | 'out'

export function objectNodeSize(): { width: number; height: number } {
  return { width: OBJECT_NODE_WIDTH, height: OBJECT_NODE_HEIGHT }
}

export function columnNodeHeight(rowCount: number, hasFooter: boolean): number {
  return COLUMN_HEADER_H + rowCount * COLUMN_ROW_H + (hasFooter ? COLUMN_FOOTER_H : 0)
}

export function columnNodeSize(rowCount: number, hasFooter: boolean): { width: number; height: number } {
  return { width: COLUMN_NODE_WIDTH, height: columnNodeHeight(rowCount, hasFooter) }
}

/** Vertical centre of row `index` — used for both the ELK port and the Handle. */
export function columnPortY(index: number): number {
  return COLUMN_HEADER_H + index * COLUMN_ROW_H + COLUMN_ROW_H / 2
}

/** CSS `top` (px) for a Handle; React Flow centres handles on `top` via translateY(-50%). */
export function columnHandleTop(index: number): number {
  return columnPortY(index)
}

/** React Flow handle id (`in:<col>` / `out:<col>`). */
export function handleId(side: PortSide, column: string): string {
  return `${side}:${column}`
}

/** Globally unique ELK port id derived from the node id and the handle id. */
export function portId(nodeId: string, side: PortSide, column: string): string {
  return `${nodeId}::${handleId(side, column)}`
}

export function elkPort(nodeId: string, side: PortSide, column: string, index: number): ElkPort {
  const centerX = side === 'in' ? 0 : COLUMN_NODE_WIDTH
  return {
    id: portId(nodeId, side, column),
    x: centerX - PORT_SIZE / 2,
    y: columnPortY(index) - PORT_SIZE / 2,
    width: PORT_SIZE,
    height: PORT_SIZE,
    layoutOptions: { 'elk.port.side': side === 'in' ? 'WEST' : 'EAST' },
  }
}
