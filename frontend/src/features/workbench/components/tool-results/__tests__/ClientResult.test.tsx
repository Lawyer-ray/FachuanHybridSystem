import { render, screen } from '@testing-library/react'
import { ClientResult } from '../ClientResult'

describe('ClientResult', () => {
  const baseProps = {
    input: {},
    toolName: 'list_clients',
  }

  it('renders "未找到客户" when output is empty', () => {
    render(<ClientResult {...baseProps} output={[]} />)
    expect(screen.getByText('未找到客户')).toBeInTheDocument()
  })

  it('renders client count for list results', () => {
    const output = {
      results: [
        { name: 'Alice', phone: '00000000000' },
        { name: 'Bob', phone: '00000000001' },
      ],
    }
    render(<ClientResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 位客户')).toBeInTheDocument()
  })

  it('renders single client detail for get_client', () => {
    const output = {
      name: 'Alice',
      client_type: '个人',
      phone: '00000000000',
      email: 'alice@example.com',
    }
    render(<ClientResult input={{}} toolName="get_client" output={output} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('00000000000')).toBeInTheDocument()
    expect(screen.getByText('alice@example.com')).toBeInTheDocument()
  })

  it('renders compact client name in list', () => {
    const output = {
      results: [{ name: 'Alice', phone: '00000000000' }],
    }
    render(<ClientResult {...baseProps} output={output} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('renders property clue results', () => {
    const output = {
      results: [{ description: 'Property A', value: 50000 }],
    }
    render(<ClientResult input={{}} toolName="list_property_clues" output={output} />)
    expect(screen.getByText('Property A')).toBeInTheDocument()
    expect(screen.getByText('共 1 条线索')).toBeInTheDocument()
  })

  it('shows "未找到财产线索" when empty', () => {
    render(<ClientResult input={{}} toolName="list_property_clues" output={[]} />)
    expect(screen.getByText('未找到财产线索')).toBeInTheDocument()
  })

  it('shows "未命名" when name is missing', () => {
    render(<ClientResult input={{}} toolName="get_client" output={{}} />)
    expect(screen.getByText('未命名')).toBeInTheDocument()
  })

  it('truncates more than 5 clients', () => {
    const output = {
      results: Array.from({ length: 8 }, (_, i) => ({ name: `Client ${i}` })),
    }
    render(<ClientResult {...baseProps} output={output} />)
    expect(screen.getByText('...还有 3 位')).toBeInTheDocument()
  })
})
