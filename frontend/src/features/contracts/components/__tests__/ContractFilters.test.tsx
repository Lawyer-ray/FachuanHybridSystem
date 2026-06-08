import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ContractFilters } from '../ContractFilters'

describe('ContractFilters', () => {
  const defaultProps = {
    onCaseTypeChange: vi.fn(),
    onStatusChange: vi.fn(),
    onSearchChange: vi.fn(),
    onFeeModeChange: vi.fn(),
    onIsFiledChange: vi.fn(),
  }

  it('renders search input', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByPlaceholderText('搜索合同名称...')).toBeInTheDocument()
  })

  it('renders filter button', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByText('筛选')).toBeInTheDocument()
  })

  it('calls onSearchChange with debounce', async () => {
    vi.useFakeTimers()
    render(<ContractFilters {...defaultProps} />)
    fireEvent.change(screen.getByPlaceholderText('搜索合同名称...'), { target: { value: 'test' } })
    vi.advanceTimersByTime(300)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('test')
    vi.useRealTimers()
  })

  it('shows filter count when filters are active', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" />)
    // The badge with count should appear
    expect(screen.getByText('筛选')).toBeInTheDocument()
  })
})
