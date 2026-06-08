vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...p }: Record<string, unknown>) => <span {...p}>{children}</span>,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr />,
}))

vi.mock('lucide-react', () => ({
  Search: (p: Record<string, unknown>) => <svg data-testid="search-icon" {...p} />,
  X: (p: Record<string, unknown>) => <svg data-testid="x-icon" {...p} />,
  SlidersHorizontal: (p: Record<string, unknown>) => <svg data-testid="sliders-icon" {...p} />,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { ClientFilters } from '../ClientFilters'

describe('ClientFilters', () => {
  const defaultProps = {
    search: '',
    onSearchChange: vi.fn(),
    clientType: undefined as string | undefined,
    onClientTypeChange: vi.fn(),
    isOurClient: undefined as boolean | undefined,
    onIsOurClientChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders search input', () => {
    render(<ClientFilters {...defaultProps} />)
    expect(screen.getByPlaceholderText('搜索姓名、手机号、身份证号...')).toBeInTheDocument()
  })

  it('renders filter button', () => {
    render(<ClientFilters {...defaultProps} />)
    expect(screen.getByText('筛选')).toBeInTheDocument()
  })

  it('calls onSearchChange when search input changes', () => {
    render(<ClientFilters {...defaultProps} />)
    const input = screen.getByPlaceholderText('搜索姓名、手机号、身份证号...')
    fireEvent.change(input, { target: { value: 'test' } })
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('test')
  })

  it('shows clear search button when search has value', () => {
    render(<ClientFilters {...defaultProps} search="test" />)
    const clearBtn = screen.getByText('清除搜索').closest('button')
    expect(clearBtn).toBeInTheDocument()
  })

  it('calls onSearchChange with empty string when clear button clicked', () => {
    render(<ClientFilters {...defaultProps} search="test" />)
    const clearBtn = screen.getByText('清除搜索').closest('button')!
    fireEvent.click(clearBtn)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('')
  })

  it('shows active filter count when filters are set', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" />)
    // Badge should show count
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows filter chip options for client type', () => {
    render(<ClientFilters {...defaultProps} />)
    const allButtons = screen.getAllByText('全部')
    expect(allButtons.length).toBeGreaterThanOrEqual(2) // One for type, one for 我方
    expect(screen.getByText('自然人')).toBeInTheDocument()
    expect(screen.getByText('法人')).toBeInTheDocument()
    expect(screen.getByText('非法人组织')).toBeInTheDocument()
  })

  it('shows filter chip options for 我方当事人', () => {
    render(<ClientFilters {...defaultProps} />)
    expect(screen.getByText('非我方当事人')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '我方当事人' })).toBeInTheDocument()
  })

  it('shows clear all button when active filters exist', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" />)
    expect(screen.getByText('清除所有筛选')).toBeInTheDocument()
  })
})
