import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { DataGrid, type GridColumn } from './DataGrid'

interface Row {
  name: string
  rows: number
}

const DATA: Row[] = [
  { name: 'b', rows: 2 },
  { name: 'a', rows: 1 },
  { name: 'c', rows: 3 },
]

const COLUMNS: GridColumn<Row>[] = [
  { id: 'name', header: 'Name', cell: (r) => r.name, sortValue: (r) => r.name },
  { id: 'rows', header: 'Rows', cell: (r) => r.rows, sortValue: (r) => r.rows },
  { id: 'note', header: 'Note', cell: () => '—' },
]

function renderGrid() {
  return render(
    <MemoryRouter>
      <DataGrid aria-label="Test grid" data={DATA} columns={COLUMNS} rowKey={(r) => r.name} />
    </MemoryRouter>,
  )
}

/** First-cell text of every body row, in render order. */
function bodyNames(): Array<string | null> {
  const [, body] = screen.getAllByRole('rowgroup')
  return within(body!)
    .getAllByRole('row')
    .map((r) => within(r).getAllByRole('cell')[0]!.textContent)
}

describe('DataGrid sortable headers', () => {
  it('renders sortable headers as real buttons and non-sortable ones as plain text', () => {
    renderGrid()
    expect(screen.getByRole('button', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rows' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Note' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Note' })).toBeInTheDocument()
  })

  it('cycles the sort from the keyboard and reflects it in aria-sort', async () => {
    const user = userEvent.setup()
    renderGrid()
    const header = screen.getByRole('columnheader', { name: 'Name' })
    expect(header).not.toHaveAttribute('aria-sort')
    expect(bodyNames()).toEqual(['b', 'a', 'c'])

    await user.tab()
    expect(screen.getByRole('button', { name: 'Name' })).toHaveFocus()

    await user.keyboard('{Enter}')
    expect(header).toHaveAttribute('aria-sort', 'ascending')
    expect(bodyNames()).toEqual(['a', 'b', 'c'])

    await user.keyboard(' ')
    expect(header).toHaveAttribute('aria-sort', 'descending')
    expect(bodyNames()).toEqual(['c', 'b', 'a'])

    await user.keyboard('{Enter}')
    expect(header).not.toHaveAttribute('aria-sort')
    expect(bodyNames()).toEqual(['b', 'a', 'c'])
  })

  it('still sorts with the mouse', async () => {
    const user = userEvent.setup()
    renderGrid()
    await user.click(screen.getByRole('button', { name: 'Rows' }))
    expect(screen.getByRole('columnheader', { name: 'Rows' })).toHaveAttribute('aria-sort', 'ascending')
    expect(bodyNames()).toEqual(['a', 'b', 'c'])
  })
})
