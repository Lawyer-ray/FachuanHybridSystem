import { render, screen } from '@testing-library/react'
import { CaseFilters } from '../CaseFilters'

vi.mock('../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return {
    ...actual,
    SIMPLE_CASE_TYPE_LABELS: {
      litigation: { zh: '诉讼' },
      non_litigation: { zh: '非诉' },
    },
    CASE_STATUS_LABELS: {
      active: { zh: '进行中' },
      closed: { zh: '已结案' },
    },
  }
})

describe('CaseFilters', () => {
  const defaultProps = {
    filters: {},
    onFiltersChange: vi.fn(),
  }

  it('renders two filter dropdowns', () => {
    render(<CaseFilters {...defaultProps} />)
    expect(screen.getAllByRole('combobox').length).toBe(2)
  })

  it('renders with default filter values', () => {
    const { container } = render(<CaseFilters {...defaultProps} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders with active filters', () => {
    render(<CaseFilters filters={{ case_type: 'litigation', status: 'active' }} onFiltersChange={vi.fn()} />)
    expect(screen.getAllByRole('combobox').length).toBe(2)
  })

  it('renders with empty onFiltersChange callback', () => {
    expect(() => {
      render(<CaseFilters filters={{}} onFiltersChange={vi.fn()} />)
    }).not.toThrow()
  })
})
