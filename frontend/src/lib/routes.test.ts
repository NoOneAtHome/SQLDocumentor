import { describe, expect, it } from 'vitest'
import { routes } from './routes'

const ref = { db: 'AdventureWorks2022', schema: 'Sales', kind: 'table', name: 'SalesOrderHeader' } as const

describe('routes', () => {
  it('builds the static and scan-scoped paths', () => {
    expect(routes.home()).toBe('/')
    expect(routes.settings()).toBe('/settings')
    expect(routes.connectionScans('local-aw')).toBe('/connections/local-aw/scans')
    expect(routes.scan(3)).toBe('/s/3')
    expect(routes.db(3, 'AdventureWorks2022')).toBe('/s/3/db/AdventureWorks2022')
    expect(routes.schema(3, 'AdventureWorks2022', 'Sales')).toBe('/s/3/db/AdventureWorks2022/Sales')
    expect(routes.kindList(3, 'AdventureWorks2022', 'Sales', 'view')).toBe(
      '/s/3/db/AdventureWorks2022/Sales/view',
    )
    expect(routes.stats(3, 'missing-indexes')).toBe('/s/3/stats/missing-indexes')
  })

  it('builds object detail paths with an optional tab', () => {
    expect(routes.object(3, ref)).toBe('/s/3/db/AdventureWorks2022/Sales/table/SalesOrderHeader')
    expect(routes.object(3, ref, 'columns')).toBe(
      '/s/3/db/AdventureWorks2022/Sales/table/SalesOrderHeader/columns',
    )
    expect(routes.object(3, ref, 'overview')).toBe(
      '/s/3/db/AdventureWorks2022/Sales/table/SalesOrderHeader',
    )
  })

  it('falls back to the id-based detail page when the object has no db or schema', () => {
    // External objects (linked servers, unconfigured databases) only carry a name + id. A
    // name-based path would contain empty segments that no `:param` route can match.
    const external = { id: 512, db: null, schema: null, kind: 'external', name: 'RemoteServer.dbo.Foo' }
    expect(routes.object(2, external)).toBe('/s/2/object/512')
    expect(routes.object(2, external, 'lineage')).toBe('/s/2/object/512/lineage')
    expect(routes.object(2, external, 'overview')).toBe('/s/2/object/512')
    expect(routes.object(2, { ...external, db: 'AdventureWorks2022', schema: '' })).toBe('/s/2/object/512')
    expect(routes.object(2, { ...external, db: '', schema: 'dbo' })).toBe('/s/2/object/512')
    // Fully addressed objects keep the name-based path (stable across scans) even when an id is known.
    expect(routes.object(2, { ...ref, id: 99 })).toBe('/s/2/db/AdventureWorks2022/Sales/table/SalesOrderHeader')
    expect(routes.objectById(2, 512)).toBe('/s/2/object/512')
    expect(routes.objectById('2', 512, 'notes')).toBe('/s/2/object/512/notes')
  })

  it('encodes every segment with encodeURIComponent', () => {
    expect(routes.object('7', { ...ref, name: '[Order Details]' })).toBe(
      '/s/7/db/AdventureWorks2022/Sales/table/%5BOrder%20Details%5D',
    )
    expect(routes.object(7, { ...ref, schema: 'a/b', name: 'c?d' })).toBe(
      '/s/7/db/AdventureWorks2022/a%2Fb/table/c%3Fd',
    )
    expect(routes.connectionScans('my conn')).toBe('/connections/my%20conn/scans')
  })

  it('builds lineage explorer URLs from params, omitting defaults', () => {
    const minimal = routes.lineage(3, { ...ref })
    const url = new URL(minimal, 'http://x')
    expect(url.pathname).toBe('/s/3/lineage')
    expect(url.searchParams.get('db')).toBe('AdventureWorks2022')
    expect(url.searchParams.get('schema')).toBe('Sales')
    expect(url.searchParams.get('kind')).toBe('table')
    expect(url.searchParams.get('name')).toBe('SalesOrderHeader')
    expect(url.searchParams.has('depth')).toBe(false)
    expect(url.searchParams.has('dir')).toBe(false)
    expect(url.searchParams.has('level')).toBe(false)

    const full = new URL(
      routes.lineage(3, {
        ...ref,
        name: '[Order Details]',
        level: 'column',
        col: 'FirstName',
        dir: 'up',
        depth: 3,
        types: ['table', 'view'],
        schemas: ['Sales'],
        cascaded: false,
        external: false,
      }),
      'http://x',
    )
    expect(full.searchParams.get('name')).toBe('[Order Details]')
    expect(full.searchParams.get('level')).toBe('column')
    expect(full.searchParams.get('col')).toBe('FirstName')
    expect(full.searchParams.get('dir')).toBe('up')
    expect(full.searchParams.get('depth')).toBe('3')
    expect(full.searchParams.get('types')).toBe('table,view')
    expect(full.searchParams.get('schemas')).toBe('Sales')
    expect(full.searchParams.get('cascaded')).toBe('0')
    expect(full.searchParams.get('external')).toBe('0')
  })
})
