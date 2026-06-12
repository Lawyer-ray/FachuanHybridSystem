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

describe('ClientFilters - coverage improvements', () => {
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

  // ========== activeFilterCount - covers line 53 ==========

  it('shows filter count of 2 when both clientType and isOurClient are set', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" isOurClient={true} />)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows filter count of 1 when only isOurClient is set', () => {
    render(<ClientFilters {...defaultProps} isOurClient={true} />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('shows filter count of 1 when only clientType is set', () => {
    render(<ClientFilters {...defaultProps} clientType="legal" />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('does not show filter count when isOurClient is false (falsy)', () => {
    render(<ClientFilters {...defaultProps} isOurClient={false} />)
    // false is falsy, so isOurClient !== undefined ? isOurClient : null => null => filtered out
    expect(screen.queryByText('1')).not.toBeInTheDocument()
  })

  // ========== clearAll - covers lines 56-58 ==========

  it('calls onClientTypeChange and onIsOurClientChange with undefined when clear all is clicked', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" isOurClient={true} />)
    fireEvent.click(screen.getByText('清除所有筛选'))
    expect(defaultProps.onClientTypeChange).toHaveBeenCalledWith(undefined)
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(undefined)
  })

  // ========== FilterChip interactions - covers toggle behavior ==========

  it('clicking client type chip toggles filter', () => {
    render(<ClientFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('自然人'))
    expect(defaultProps.onClientTypeChange).toHaveBeenCalledWith('natural')
  })

  it('clicking active client type chip clears filter', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" />)
    fireEvent.click(screen.getByText('自然人'))
    expect(defaultProps.onClientTypeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "我方当事人" chip sets filter', () => {
    render(<ClientFilters {...defaultProps} />)
    // "我方当事人" appears as both a heading and a chip button
    const chips = screen.getAllByText('我方当事人')
    // The last one is the filter chip button
    fireEvent.click(chips[chips.length - 1])
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(true)
  })

  it('clicking active "我方当事人" chip clears filter', () => {
    render(<ClientFilters {...defaultProps} isOurClient={true} />)
    const chips = screen.getAllByText('我方当事人')
    fireEvent.click(chips[chips.length - 1])
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "非我方当事人" chip sets filter to false', () => {
    render(<ClientFilters {...defaultProps} />)
    fireEvent.click(screen.getByText('非我方当事人'))
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(false)
  })

  it('clicking active "非我方当事人" chip clears filter', () => {
    render(<ClientFilters {...defaultProps} isOurClient={false} />)
    fireEvent.click(screen.getByText('非我方当事人'))
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "全部" type chip clears type filter', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" />)
    const allButtons = screen.getAllByText('全部')
    fireEvent.click(allButtons[0])
    expect(defaultProps.onClientTypeChange).toHaveBeenCalledWith(undefined)
  })

  it('clicking "全部" isOurClient chip clears isOurClient filter', () => {
    render(<ClientFilters {...defaultProps} isOurClient={true} />)
    const allButtons = screen.getAllByText('全部')
    fireEvent.click(allButtons[1])
    expect(defaultProps.onIsOurClientChange).toHaveBeenCalledWith(undefined)
  })

  // ========== Search with value shows clear button ==========

  it('shows clear search button when search has value', () => {
    render(<ClientFilters {...defaultProps} search="test" />)
    const clearBtn = screen.getByText('清除搜索').closest('button')
    expect(clearBtn).toBeInTheDocument()
  })

  it('hides clear search button when search is empty', () => {
    render(<ClientFilters {...defaultProps} search="" />)
    expect(screen.queryByText('清除搜索')).not.toBeInTheDocument()
  })

  // ========== activeFilterCount with both filters and isOurClient false ==========

  it('shows correct count when clientType is set and isOurClient is false', () => {
    render(<ClientFilters {...defaultProps} clientType="natural" isOurClient={false} />)
    // clientType contributes 1, isOurClient=false is null (falsy) => count = 1
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  // ========== No clear all button when no active filters ==========

  it('does not show clear all button when no active filters', () => {
    render(<ClientFilters {...defaultProps} />)
    expect(screen.queryByText('清除所有筛选')).not.toBeInTheDocument()
  })

  // ========== All type chips rendered ==========

  it('renders all client type filter chips', () => {
    render(<ClientFilters {...defaultProps} />)
    expect(screen.getByText('自然人')).toBeInTheDocument()
    expect(screen.getByText('法人')).toBeInTheDocument()
    expect(screen.getByText('非法人组织')).toBeInTheDocument()
  })

  // ========== All isOurClient chips rendered ==========

  it('renders all isOurClient filter chips', () => {
    render(<ClientFilters {...defaultProps} />)
    // "我方当事人" appears as heading and chip
    const chips = screen.getAllByText('我方当事人')
    expect(chips.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('非我方当事人')).toBeInTheDocument()
  })

  // ========== Search input change ==========

  it('calls onSearchChange on input change', () => {
    render(<ClientFilters {...defaultProps} />)
    fireEvent.change(screen.getByPlaceholderText('搜索姓名、手机号、身份证号...'), { target: { value: 'abc' } })
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('abc')
  })

  // ========== Clear search button click ==========

  it('clears search when clear button is clicked', () => {
    render(<ClientFilters {...defaultProps} search="abc" />)
    fireEvent.click(screen.getByText('清除搜索').closest('button')!)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('')
  })
})
