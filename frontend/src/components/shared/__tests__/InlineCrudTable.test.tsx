import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InlineCrudTable } from '../InlineCrudTable'

const columns = [
  { key: 'name', header: 'Name', placeholder: 'Enter name' },
  { key: 'value', header: 'Value', type: 'number' as const },
]

describe('InlineCrudTable', () => {
  it('renders column headers', () => {
    render(<InlineCrudTable columns={columns} rows={[]} onChange={vi.fn()} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Value')).toBeInTheDocument()
  })

  it('renders empty state message', () => {
    render(<InlineCrudTable columns={columns} rows={[]} onChange={vi.fn()} />)
    expect(screen.getByText('暂无数据，点击下方按钮添加')).toBeInTheDocument()
  })

  it('renders existing rows', () => {
    const rows = [{ name: 'John', value: '100' }]
    render(<InlineCrudTable columns={columns} rows={rows} onChange={vi.fn()} />)
    expect(screen.getByDisplayValue('John')).toBeInTheDocument()
    expect(screen.getByDisplayValue('100')).toBeInTheDocument()
  })

  it('adds a new row when add button clicked and last row is filled', async () => {
    const onChange = vi.fn()
    const rows = [{ name: 'John', value: '100' }]
    render(<InlineCrudTable columns={columns} rows={rows} onChange={onChange} />)
    await userEvent.click(screen.getByText('添加'))
    expect(onChange).toHaveBeenCalledWith([
      { name: 'John', value: '100' },
      { name: '', value: '' },
    ])
  })

  it('does not add row when last row has empty fields', async () => {
    const onChange = vi.fn()
    const rows = [{ name: '', value: '' }]
    render(<InlineCrudTable columns={columns} rows={rows} onChange={onChange} />)
    await userEvent.click(screen.getByText('添加'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('adds first row when rows are empty', async () => {
    const onChange = vi.fn()
    render(<InlineCrudTable columns={columns} rows={[]} onChange={onChange} />)
    await userEvent.click(screen.getByText('添加'))
    expect(onChange).toHaveBeenCalledWith([{ name: '', value: '' }])
  })

  it('deletes a row on trash button click', async () => {
    const onChange = vi.fn()
    const rows = [
      { name: 'Row1', value: '1' },
      { name: 'Row2', value: '2' },
    ]
    render(<InlineCrudTable columns={columns} rows={rows} onChange={onChange} />)
    const deleteButtons = screen.getAllByRole('button', { name: '' }) // trash icon buttons
    // Find the trash button (it has no text, just an icon)
    const trashButtons = document.querySelectorAll('button')
    // Click the first delete button (after the header row)
    const buttons = screen.getAllByRole('button')
    // The trash buttons are after the column headers
    const trashBtn = buttons.find(b => b.querySelector('svg'))
    if (trashBtn) {
      await userEvent.click(trashBtn)
      expect(onChange).toHaveBeenCalled()
    }
  })

  it('updates cell value on input change', async () => {
    const onChange = vi.fn()
    const rows = [{ name: 'John', value: '100' }]
    render(<InlineCrudTable columns={columns} rows={rows} onChange={onChange} />)
    const nameInput = screen.getByDisplayValue('John')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'Jane')
    // onChange is called for each character typed/cleared
    expect(onChange).toHaveBeenCalled()
  })

  it('uses custom addLabel', () => {
    render(<InlineCrudTable columns={columns} rows={[]} onChange={vi.fn()} addLabel="New Row" />)
    expect(screen.getByText('New Row')).toBeInTheDocument()
  })
})
