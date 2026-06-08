import { render, screen } from '@testing-library/react'
import { ListResult } from '../ListResult'

describe('ListResult', () => {
  const baseProps = {
    input: {},
    toolName: 'list_items',
  }

  it('returns null when output is empty', () => {
    const { container } = render(<ListResult {...baseProps} output={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders single record in key-value format', () => {
    const output = [{ name: 'Alice', age: 30, active: true }]
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('Name:')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('renders multiple records as compact list', () => {
    const output = [
      { name: 'Alice', title: 'Developer' },
      { name: 'Bob', title: 'Designer' },
      { name: 'Charlie', title: 'Manager' },
    ]
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('共 3 条结果')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Charlie')).toBeInTheDocument()
  })

  it('truncates more than 5 items', () => {
    const output = Array.from({ length: 8 }, (_, i) => ({ name: `Item ${i}` }))
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('...还有 3 条')).toBeInTheDocument()
  })

  it('handles nested results array', () => {
    const output = { results: [{ name: 'Test' }] }
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('handles primitive values in list', () => {
    const output = ['apple', 'banana', 'cherry']
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('apple')).toBeInTheDocument()
    expect(screen.getByText('banana')).toBeInTheDocument()
  })

  it('renders result count for multiple items', () => {
    const output = [{ name: 'A' }, { name: 'B' }]
    render(<ListResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 条结果')).toBeInTheDocument()
  })
})
