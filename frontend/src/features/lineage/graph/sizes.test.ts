import { describe, expect, it } from 'vitest'
import {
  COLUMN_FOOTER_H,
  COLUMN_HEADER_H,
  COLUMN_NODE_WIDTH,
  COLUMN_ROW_H,
  OBJECT_NODE_HEIGHT,
  OBJECT_NODE_WIDTH,
  columnHandleTop,
  columnNodeHeight,
  columnNodeSize,
  columnPortY,
  elkPort,
  handleId,
  objectNodeSize,
  portId,
} from './sizes'

describe('sizes', () => {
  it('object node cards have the fixed 240×64 footprint from the spec', () => {
    expect(OBJECT_NODE_WIDTH).toBe(240)
    expect(OBJECT_NODE_HEIGHT).toBe(64)
    expect(objectNodeSize()).toEqual({ width: 240, height: 64 })
  })

  it('column nodes are 260 wide with 24px rows', () => {
    expect(COLUMN_NODE_WIDTH).toBe(260)
    expect(COLUMN_ROW_H).toBe(24)
    expect(columnNodeHeight(0, false)).toBe(COLUMN_HEADER_H)
    expect(columnNodeHeight(3, false)).toBe(COLUMN_HEADER_H + 3 * COLUMN_ROW_H)
    expect(columnNodeHeight(3, true)).toBe(COLUMN_HEADER_H + 3 * COLUMN_ROW_H + COLUMN_FOOTER_H)
    expect(columnNodeSize(2, true)).toEqual({
      width: 260,
      height: COLUMN_HEADER_H + 2 * COLUMN_ROW_H + COLUMN_FOOTER_H,
    })
  })

  it('ELK port y equals the CSS top of the matching Handle for every row', () => {
    for (let i = 0; i < 40; i++) {
      expect(columnPortY(i)).toBe(COLUMN_HEADER_H + i * COLUMN_ROW_H + COLUMN_ROW_H / 2)
      expect(columnHandleTop(i)).toBe(columnPortY(i))
      const inPort = elkPort('o:1', 'in', 'FirstName', i)
      const outPort = elkPort('o:1', 'out', 'FirstName', i)
      expect(inPort.y! + inPort.height! / 2).toBe(columnHandleTop(i))
      expect(outPort.y! + outPort.height! / 2).toBe(columnHandleTop(i))
    }
  })

  it('places in-ports on the west edge and out-ports on the east edge', () => {
    const inPort = elkPort('o:1', 'in', 'FirstName', 0)
    const outPort = elkPort('o:1', 'out', 'FirstName', 0)
    expect(inPort.x! + inPort.width! / 2).toBe(0)
    expect(outPort.x! + outPort.width! / 2).toBe(COLUMN_NODE_WIDTH)
    expect(inPort.layoutOptions?.['elk.port.side']).toBe('WEST')
    expect(outPort.layoutOptions?.['elk.port.side']).toBe('EAST')
  })

  it('derives globally unique ELK port ids from the React Flow handle ids', () => {
    expect(handleId('in', 'FirstName')).toBe('in:FirstName')
    expect(handleId('out', 'Last Name')).toBe('out:Last Name')
    expect(portId('o:12', 'in', 'FirstName')).toBe('o:12::in:FirstName')
    expect(elkPort('o:12', 'out', 'X', 0).id).toBe(portId('o:12', 'out', 'X'))
  })
})
