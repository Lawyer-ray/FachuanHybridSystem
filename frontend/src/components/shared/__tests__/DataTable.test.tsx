import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { DataTable } from '../DataTable'

interface TestRow {
  id: number
  name: string
  status: string
}

const columns = [
  { key: 'id', header: 'ID' },
  { key: 'name', header: 'Name' },
  { key: 'status', header: 'Status' },
]

const rows: TestRow[] = [
  { id: 1, name: 'Alice', status: 'active' },
  { id: 2, name: 'Bob', status: 'pending' },
]

const rowKey = (row: TestRow) => row.id

describe('DataTable', () => {
  it('renders column headers', () => {
    render(<DataTable columns={columns} data={rows} rowKey={rowKey} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('renders data rows', () => {
    render(<DataTable columns={columns} data={rows} rowKey={rowKey} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('renders empty state when data is empty', () => {
    render(<DataTable columns={columns} data={[]} rowKey={rowKey} />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('renders custom empty text', () => {
    render(<DataTable columns={columns} data={[]} rowKey={rowKey} emptyText="No records" />)
    expect(screen.getByText('No records')).toBeInTheDocument()
  })

  it('calls onRowClick when row is clicked', async () => {
    const onRowClick = vi.fn()
    render(<DataTable columns={columns} data={rows} rowKey={rowKey} onRowClick={onRowClick} />)
    await userEvent.click(screen.getByText('Alice'))
    expect(onRowClick).toHaveBeenCalledWith(rows[0])
  })

  it('uses custom render function', () => {
    const customColumns = [
      { key: 'name', header: 'Name', render: (row: TestRow) => `Custom: ${row.name}` },
    ]
    render(<DataTable columns={customColumns} data={rows} rowKey={rowKey} />)
    expect(screen.getByText('Custom: Alice')).toBeInTheDocument()
  })

  it('shows selection checkboxes when onSelectChange provided', () => {
    const onSelectChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={rows}
        rowKey={rowKey}
        selectedKeys={new Set()}
        onSelectChange={onSelectChange}
      />
    )
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(3) // 1 select all + 2 row checkboxes
  })

  it('selects all rows on header checkbox click', async () => {
    const onSelectChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={rows}
        rowKey={rowKey}
        selectedKeys={new Set()}
        onSelectChange={onSelectChange}
      />
    )
    const checkboxes = screen.getAllByRole('checkbox')
    await userEvent.click(checkboxes[0])
    expect(onSelectChange).toHaveBeenCalledWith(new Set([1, 2]))
  })

  it('selects individual row checkbox', async () => {
    const onSelectChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={rows}
        rowKey={rowKey}
        selectedKeys={new Set()}
        onSelectChange={onSelectChange}
      />
    )
    const checkboxes = screen.getAllByRole('checkbox')
    await userEvent.click(checkboxes[1])
    expect(onSelectChange).toHaveBeenCalled()
  })

  it('applies custom className', () => {
    const { container } = render(
      <DataTable columns={columns} data={[]} rowKey={rowKey} className="custom" />
    )
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain('custom')
  })

  it('renders column with width style', () => {
    const widthColumns = [
      { key: 'name', header: 'Name', width: '200px' },
    ]
    render(<DataTable columns={widthColumns} data={rows} rowKey={rowKey} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
  })

  it('deselects all rows when header checkbox is unchecked', async () => {
    const onSelectChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={rows}
        rowKey={rowKey}
        selectedKeys={new Set([1, 2])}
        onSelectChange={onSelectChange}
      />
    )
    const checkboxes = screen.getAllByRole('checkbox')
    // The first checkbox is the "select all" checkbox - uncheck it
    await userEvent.click(checkboxes[0])
    expect(onSelectChange).toHaveBeenCalledWith(new Set())
  })

  it('deselects a single row when checkbox is unchecked', async () => {
    const onSelectChange = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={rows}
        rowKey={rowKey}
        selectedKeys={new Set([1, 2])}
        onSelectChange={onSelectChange}
      />
    )
    const checkboxes = screen.getAllByRole('checkbox')
    // Click the second checkbox (row 1) to deselect it
    await userEvent.click(checkboxes[1])
    expect(onSelectChange).toHaveBeenCalled()
    // Should have removed key 1 from the set
    const calledWith = onSelectChange.mock.calls[0][0]
    expect(calledWith.has(2)).toBe(true)
    expect(calledWith.has(1)).toBe(false)
  })

  it('renders with no data and custom rowKey', () => {
    const { container } = render(
      <DataTable columns={columns} data={[]} rowKey={rowKey} emptyText="空数据" />
    )
    expect(screen.getByText('空数据')).toBeInTheDocument()
    expect(container.querySelector('table')).toBeInTheDocument()
  })

  it('renders default fallback when column value is missing', () => {
    const dataWithMissing = [{ id: 1, name: 'Test', status: undefined }] as any[]
    render(<DataTable columns={columns} data={dataWithMissing} rowKey={rowKey} />)
    expect(screen.getByText('Test')).toBeInTheDocument()
  })
})
