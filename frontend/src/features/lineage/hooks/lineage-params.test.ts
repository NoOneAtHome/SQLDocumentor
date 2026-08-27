import { describe, expect, it } from 'vitest'
import { DEFAULT_LINEAGE_PARAMS, parseLineageParams, serializeLineageParams } from './lineage-params'

describe('lineage params codec', () => {
  it('parses defaults when nothing is set', () => {
    const p = parseLineageParams(new URLSearchParams(''))
    expect(p).toEqual({ ...DEFAULT_LINEAGE_PARAMS, db: '', schema: '', kind: '', name: '' })
  })

  it('parses and clamps every explorer control', () => {
    const p = parseLineageParams(
      new URLSearchParams(
        'db=AW&schema=Sales&kind=view&name=vIndividualCustomer&col=FirstName&level=column&dir=up&depth=9&types=table,view&schemas=Sales,Person&cascaded=0&external=0&edges=fk,trigger',
      ),
    )
    expect(p.db).toBe('AW')
    expect(p.kind).toBe('view')
    expect(p.col).toBe('FirstName')
    expect(p.level).toBe('column')
    expect(p.dir).toBe('up')
    expect(p.depth).toBe(5)
    expect(p.types).toEqual(['table', 'view'])
    expect(p.schemas).toEqual(['Sales', 'Person'])
    expect(p.cascaded).toBe(false)
    expect(p.external).toBe(false)
    expect(p.edges).toEqual(['fk', 'trigger'])
  })

  it('ignores garbage values', () => {
    const p = parseLineageParams(new URLSearchParams('dir=sideways&depth=abc&level=nope&types=bogus'))
    expect(p.dir).toBe('both')
    expect(p.depth).toBe(2)
    expect(p.level).toBe('object')
    expect(p.types).toEqual([])
  })

  it('round-trips through serialize without emitting defaults', () => {
    const p = parseLineageParams(
      new URLSearchParams('db=AW&schema=Sales&kind=view&name=v&dir=down&depth=3&cascaded=0'),
    )
    const q = serializeLineageParams(p)
    expect(q.get('dir')).toBe('down')
    expect(q.get('depth')).toBe('3')
    expect(q.get('cascaded')).toBe('0')
    expect(q.has('external')).toBe(false)
    expect(q.has('level')).toBe(false)
    expect(q.has('col')).toBe(false)
    expect(parseLineageParams(q)).toEqual(p)
  })
})
