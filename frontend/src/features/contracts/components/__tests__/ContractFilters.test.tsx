import { render, screen, fireEvent } from '@testing-library/react'
import { ContractFilters } from '../ContractFilters'
import type { CaseType, ContractStatus, FeeMode } from '../../types'

// ── Mocks ──

vi.mock('lucide-react', () => ({
  Search: (p: Record<string, unknown>) => <svg data-testid="search-icon" {...p} />,
  SlidersHorizontal: (p: Record<string, unknown>) => <svg data-testid="sliders-icon" {...p} />,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (
    <div data-testid="popover" data-open={open}>{children}</div>
  ),
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div data-testid="popover-content">{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr data-testid="separator" />,
}))

describe('ContractFilters', () => {
  const defaultProps = {
    onCaseTypeChange: vi.fn(),
    onStatusChange: vi.fn(),
    onSearchChange: vi.fn(),
    onFeeModeChange: vi.fn(),
    onIsFiledChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders search input and filter button', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByPlaceholderText('搜索合同名称...')).toBeInTheDocument()
    expect(screen.getByText('筛选')).toBeInTheDocument()
  })

  it('debounces search input', () => {
    render(<ContractFilters {...defaultProps} />)
    const input = screen.getByPlaceholderText('搜索合同名称...')
    fireEvent.change(input, { target: { value: 'test' } })
    // Not called immediately
    expect(defaultProps.onSearchChange).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('test')
  })

  it('shows filter count badge when filters active', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows correct count with multiple filters', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" status="active" feeMode="FIXED" />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('shows isFiled in filter count', () => {
    render(<ContractFilters {...defaultProps} isFiled={true} />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('does not show filter count when no filters active', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('renders filter chips for case types', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByText('民商事')).toBeInTheDocument()
    expect(screen.getByText('刑事')).toBeInTheDocument()
    expect(screen.getByText('常法顾问')).toBeInTheDocument()
  })

  it('renders filter chips for status', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByText('未签约')).toBeInTheDocument()
    expect(screen.getByText('在办')).toBeInTheDocument()
    expect(screen.getByText('已结案')).toBeInTheDocument()
    expect(screen.getByText('已归档')).toBeInTheDocument()
  })

  it('renders filter chips for fee mode', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByText('固定收费')).toBeInTheDocument()
    expect(screen.getByText('半风险收费')).toBeInTheDocument()
    expect(screen.getByText('全风险收费')).toBeInTheDocument()
    expect(screen.getByText('自定义')).toBeInTheDocument()
  })

  it('renders filed filter chips', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.getByText('已建档')).toBeInTheDocument()
    expect(screen.getByText('未建档')).toBeInTheDocument()
  })

  it('clicking case type chip calls onCaseTypeChange', () => {
    render(<ContractFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('民商事'))
    expect(defaultProps.onCaseTypeChange).toHaveBeenCalledWith('civil')
  })

  it('clicking active case type chip deselects it', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" />)
    fireEvent.click(screen.getByText('民商事'))
    expect(defaultProps.onCaseTypeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking status chip calls onStatusChange', () => {
    render(<ContractFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('在办'))
    expect(defaultProps.onStatusChange).toHaveBeenCalledWith('active')
  })

  it('clicking active status chip deselects it', () => {
    render(<ContractFilters {...defaultProps} status="active" />)
    fireEvent.click(screen.getByText('在办'))
    expect(defaultProps.onStatusChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking fee mode chip calls onFeeModeChange', () => {
    render(<ContractFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('固定收费'))
    expect(defaultProps.onFeeModeChange).toHaveBeenCalledWith('FIXED')
  })

  it('clicking active fee mode chip deselects it', () => {
    render(<ContractFilters {...defaultProps} feeMode="FIXED" />)
    fireEvent.click(screen.getByText('固定收费'))
    expect(defaultProps.onFeeModeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking filed chip calls onIsFiledChange', () => {
    render(<ContractFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('已建档'))
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(true)
  })

  it('clicking active filed chip deselects it', () => {
    render(<ContractFilters {...defaultProps} isFiled={true} />)
    fireEvent.click(screen.getByText('已建档'))
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking unfiled chip calls onIsFiledChange(false)', () => {
    render(<ContractFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('未建档'))
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(false)
  })

  it('clicking active unfiled chip deselects it', () => {
    render(<ContractFilters {...defaultProps} isFiled={false} />)
    fireEvent.click(screen.getByText('未建档'))
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(undefined)
  })

  it('clear all button clears all filters', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" status="active" feeMode="FIXED" isFiled={true} />)
    fireEvent.click(screen.getByText('清除所有筛选'))
    expect(defaultProps.onCaseTypeChange).toHaveBeenCalledWith(undefined)
    expect(defaultProps.onStatusChange).toHaveBeenCalledWith(undefined)
    expect(defaultProps.onFeeModeChange).toHaveBeenCalledWith(undefined)
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(undefined)
  })

  it('does not show clear all button when no filters active', () => {
    render(<ContractFilters {...defaultProps} />)
    expect(screen.queryByText('清除所有筛选')).not.toBeInTheDocument()
  })

  it('renders "全部" chip for each category', () => {
    render(<ContractFilters {...defaultProps} />)
    const allChips = screen.getAllByText('全部')
    // 4 categories: case type, status, fee mode, filed
    expect(allChips.length).toBe(4)
  })

  it('clicking "全部" for case type resets to undefined', () => {
    render(<ContractFilters {...defaultProps} caseType="civil" />)
    const allChips = screen.getAllByText('全部')
    fireEvent.click(allChips[0])
    expect(defaultProps.onCaseTypeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "全部" for status resets to undefined', () => {
    render(<ContractFilters {...defaultProps} status="active" />)
    const allChips = screen.getAllByText('全部')
    fireEvent.click(allChips[1])
    expect(defaultProps.onStatusChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "全部" for fee mode resets to undefined', () => {
    render(<ContractFilters {...defaultProps} feeMode="FIXED" />)
    const allChips = screen.getAllByText('全部')
    fireEvent.click(allChips[2])
    expect(defaultProps.onFeeModeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "全部" for filed resets to undefined', () => {
    render(<ContractFilters {...defaultProps} isFiled={true} />)
    const allChips = screen.getAllByText('全部')
    fireEvent.click(allChips[3])
    expect(defaultProps.onIsFiledChange).toHaveBeenCalledWith(undefined)
  })

  it('renders with default search value', () => {
    render(<ContractFilters {...defaultProps} search="initial" />)
    const input = screen.getByPlaceholderText('搜索合同名称...')
    expect(input).toHaveValue('initial')
  })

  it('handles search input with empty value', () => {
    render(<ContractFilters {...defaultProps} search="initial" />)
    const input = screen.getByPlaceholderText('搜索合同名称...')
    fireEvent.change(input, { target: { value: '' } })
    vi.advanceTimersByTime(300)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('')
  })
})
