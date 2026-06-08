import { render, screen } from '@testing-library/react'
import { CaseResult } from '../CaseResult'

vi.mock('@/lib/date', () => ({
  formatShortDate: (s: string) => s,
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (n: number) => `${n}元`,
}))

describe('CaseResult', () => {
  const baseProps = {
    input: {},
    toolName: 'list_cases',
  }

  it('renders "未找到案件" when output is empty array', () => {
    render(<CaseResult {...baseProps} output={[]} />)
    expect(screen.getByText('未找到案件')).toBeInTheDocument()
  })

  it('renders "未找到案件" when results is empty', () => {
    render(<CaseResult {...baseProps} output={{ results: [] }} />)
    expect(screen.getByText('未找到案件')).toBeInTheDocument()
  })

  it('renders case count for list results', () => {
    const output = {
      results: [
        { name: 'Case A', status: 'active' },
        { name: 'Case B', status: 'closed' },
      ],
    }
    render(<CaseResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 个案件')).toBeInTheDocument()
  })

  it('renders single case detail for get_case', () => {
    const output = {
      name: 'Test Case',
      case_type: 'litigation',
      case_number: '(2026)京01民初123号',
      status: 'active',
    }
    render(<CaseResult input={{}} toolName="get_case" output={output} />)
    expect(screen.getByText('Test Case')).toBeInTheDocument()
    expect(screen.getByText('诉讼')).toBeInTheDocument()
  })

  it('renders case name in compact view', () => {
    const output = {
      results: [
        { name: 'Case A', status: 'active' },
      ],
    }
    render(<CaseResult {...baseProps} output={output} />)
    expect(screen.getByText('Case A')).toBeInTheDocument()
  })

  it('shows "未命名案件" when name is missing', () => {
    render(<CaseResult input={{}} toolName="get_case" output={{}} />)
    expect(screen.getByText('未命名案件')).toBeInTheDocument()
  })

  it('renders parties list', () => {
    const output = {
      name: 'Case A',
      parties: [{ name: '张三' }, { name: '李四' }],
    }
    render(<CaseResult input={{}} toolName="get_case" output={output} />)
    expect(screen.getByText('张三、李四')).toBeInTheDocument()
  })

  it('truncates more than 5 items in list view', () => {
    const output = {
      results: Array.from({ length: 8 }, (_, i) => ({ name: `Case ${i}` })),
    }
    render(<CaseResult {...baseProps} output={output} />)
    expect(screen.getByText('...还有 3 个')).toBeInTheDocument()
  })
})
