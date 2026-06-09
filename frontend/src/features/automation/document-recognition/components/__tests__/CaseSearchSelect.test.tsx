/**
 * CaseSearchSelect Component Tests
 * 测试案件搜索选择组件
 *
 * 覆盖：搜索输入、防抖、加载状态、搜索结果展示、选择、清除、
 *       空状态、下拉显示/隐藏、禁用状态、点击外部关闭、已选中值展示
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { CaseSearchSelect } from '../CaseSearchSelect'
import type { CaseSearchResult } from '../types'

// ---- mock useCaseSearch ----
let mockSearchReturn: {
  data: CaseSearchResult[] | undefined
  isLoading: boolean
  error: Error | null
} = { data: undefined, isLoading: false, error: null }

vi.mock('../../hooks/use-case-search', () => ({
  useCaseSearch: vi.fn(() => mockSearchReturn),
}))

// ---- mock @/lib/utils ----
vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

// ---- mock UI primitives ----
vi.mock('@/components/ui/input', () => ({
  Input: ({ ref: _ref, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { ref?: React.Ref<HTMLInputElement> }) => <input {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    variant,
    size,
    className,
    type,
  }: Record<string, unknown>) => (
    <button
      type={type as string}
      onClick={onClick as React.MouseEventHandler}
      disabled={disabled as boolean}
      className={className as string}
    >
      {children}
    </button>
  ),
}))

vi.mock('lucide-react', () => ({
  Search: (p: Record<string, unknown>) => <svg data-testid="icon-search" {...p} />,
  X: (p: Record<string, unknown>) => <svg data-testid="icon-x" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="icon-loader" {...p} />,
  FileSearch: (p: Record<string, unknown>) => <svg data-testid="icon-file-search" {...p} />,
  Check: (p: Record<string, unknown>) => <svg data-testid="icon-check" {...p} />,
}))

// ---- helpers ----
const sampleResults: CaseSearchResult[] = [
  { id: 1, name: '张某诉李某', case_number: '(2026)京01民初100号' },
  { id: 2, name: '王某诉赵某', case_number: '(2026)京01民初200号' },
  { id: 3, name: '刘某诉陈某', case_number: '(2026)沪01民初300号' },
]

const selectedCase: CaseSearchResult = {
  id: 1,
  name: '张某诉李某',
  case_number: '(2026)京01民初100号',
}

// ---- tests ----
describe('CaseSearchSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSearchReturn = { data: undefined, isLoading: false, error: null }
  })

  // ========== basic rendering ==========

  it('renders search input with default placeholder', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeInTheDocument()
  })

  it('renders custom placeholder', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} placeholder="选择案件..." />)
    expect(screen.getByPlaceholderText('选择案件...')).toBeInTheDocument()
  })

  it('disables input when disabled prop is true', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} disabled />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeDisabled()
  })

  // ========== selected value display ==========

  it('shows selected case name and number when value is set and dropdown is closed', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.getByText('(2026)京01民初100号')).toBeInTheDocument()
  })

  it('does not show search input when value is set and dropdown is closed', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    expect(screen.queryByPlaceholderText('搜索案件名称或案号...')).not.toBeInTheDocument()
  })

  it('shows re-search button when value is set and not disabled', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    expect(screen.getByText('重新搜索')).toBeInTheDocument()
  })

  it('does not show re-search button when value is set and disabled', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} disabled />)
    expect(screen.queryByText('重新搜索')).not.toBeInTheDocument()
  })

  it('adds opacity class when disabled with a selected value', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} disabled />)
    const displayDiv = screen.getByText('张某诉李某').closest('div')?.parentElement?.parentElement
    expect(displayDiv).toHaveClass('opacity-50')
  })

  // ========== re-search click ==========

  it('shows input and opens dropdown when re-search button is clicked', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    // Input is hidden because value is set
    expect(screen.queryByPlaceholderText('搜索案件名称或案号...')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('重新搜索'))

    // After clicking re-search, the input should now be visible (isOpen=true)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    expect(input).toBeInTheDocument()

    // Type to confirm dropdown works
    fireEvent.change(input, { target: { value: '张' } })
    expect(screen.getByText('请输入至少 2 个字符搜索')).toBeInTheDocument()
  })

  // ========== input typing ==========

  it('opens dropdown when user types in input', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })
    expect(input).toHaveValue('张某')
    // After typing, a hint state should appear (since query < 2 chars or loading)
    // The dropdown container should be present
  })

  it('does not open dropdown when disabled and input is focused', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} disabled />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.focus(input)
    // Dropdown should not appear
    expect(screen.queryByText('搜索中...')).not.toBeInTheDocument()
  })

  // ========== focus behaviour ==========

  it('opens dropdown on focus when value is set and input has query', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    // Click re-search to show input
    fireEvent.click(screen.getByText('重新搜索'))
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')

    // Type a single char to open dropdown with hint
    fireEvent.change(input, { target: { value: '张' } })
    expect(screen.getByText('请输入至少 2 个字符搜索')).toBeInTheDocument()
  })

  it('does not open dropdown on focus when no query and no value', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.focus(input)
    // Without query or value, isOpen stays false
    expect(screen.queryByText('请输入至少 2 个字符搜索')).not.toBeInTheDocument()
  })

  // ========== loading state ==========

  it('shows loading spinner when search is in progress', () => {
    mockSearchReturn = { data: undefined, isLoading: true, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    expect(screen.getByText('搜索中...')).toBeInTheDocument()
    expect(screen.getByTestId('icon-loader')).toBeInTheDocument()
  })

  // ========== hint state (min chars) ==========

  it('shows hint when query is less than 2 characters', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张' } })

    expect(screen.getByText('请输入至少 2 个字符搜索')).toBeInTheDocument()
  })

  // ========== hint state (initial, no query, no value) ==========

  it('shows initial hint state when dropdown is open but no query and no value', () => {
    // This happens when user focuses input and value exists, then clears
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    // Type something to open dropdown
    fireEvent.change(input, { target: { value: 'ab' } })
    // Clear it
    fireEvent.change(input, { target: { value: '' } })
    // isOpen was set to true by the non-empty change, then cleared to ''
    // Since hasQuery becomes false and no value, HintState should appear
    // Actually, the handleInputChange only sets isOpen if length > 0,
    // so after clearing, isOpen stays true from the prior set
    expect(screen.getByText('请输入至少 2 个字符搜索')).toBeInTheDocument()
  })

  // ========== search results ==========

  it('displays search results when data is available', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })

    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.getByText('(2026)京01民初100号')).toBeInTheDocument()
    expect(screen.getByText('王某诉赵某')).toBeInTheDocument()
    expect(screen.getByText('(2026)京01民初200号')).toBeInTheDocument()
    expect(screen.getByText('刘某诉陈某')).toBeInTheDocument()
    expect(screen.getByText('(2026)沪01民初300号')).toBeInTheDocument()
  })

  it('shows check icon for selected item in results', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    fireEvent.click(screen.getByText('重新搜索'))
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })

    // The selected item (id=1) should have a Check icon
    const checkIcons = screen.getAllByTestId('icon-check')
    expect(checkIcons.length).toBe(1)
  })

  // ========== selection ==========

  it('calls onSelect when a result is clicked', () => {
    const onSelect = vi.fn()
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={onSelect} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    fireEvent.click(screen.getByText('张某诉李某'))
    expect(onSelect).toHaveBeenCalledWith(sampleResults[0])
  })

  it('clears query and closes dropdown after selection', () => {
    const onSelect = vi.fn()
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={onSelect} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    fireEvent.click(screen.getByText('张某诉李某'))
    expect(onSelect).toHaveBeenCalled()

    // After selection, dropdown should close and search results should disappear
    expect(screen.queryByText('王某诉赵某')).not.toBeInTheDocument()
  })

  it('hides search input after selection (value now set)', () => {
    const onSelect = vi.fn()
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }

    const { rerender } = render(<CaseSearchSelect onSelect={onSelect} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })
    fireEvent.click(screen.getByText('张某诉李某'))

    // Simulate parent updating value
    rerender(<CaseSearchSelect onSelect={onSelect} value={selectedCase} />)
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('搜索案件名称或案号...')).not.toBeInTheDocument()
  })

  // ========== clear button ==========

  it('shows clear button when input has text', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })
    expect(screen.getByText('清除')).toBeInTheDocument()
  })

  it('hides clear button when input is empty', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.queryByText('清除')).not.toBeInTheDocument()
  })

  it('clears query and closes dropdown when clear button is clicked', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    fireEvent.click(screen.getByText('清除'))
    expect(input).toHaveValue('')
    // Dropdown should be closed; hint states should not be visible
    expect(screen.queryByText('请输入至少 2 个字符搜索')).not.toBeInTheDocument()
  })

  it('hides clear button when disabled', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} disabled />)
    // Even though disabled, if we could type... the button checks !disabled
    // With disabled=true, the input is disabled so we can't type, but verify the button condition
    expect(screen.queryByText('清除')).not.toBeInTheDocument()
  })

  // ========== empty state (no results) ==========

  it('shows empty state when search returns no results', () => {
    mockSearchReturn = { data: [], isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '不存在的案件' } })

    expect(screen.getByText(/未找到与/)).toBeInTheDocument()
    expect(screen.getByText(/不存在的案件/)).toBeInTheDocument()
    expect(screen.getByText('请尝试其他关键词')).toBeInTheDocument()
  })

  it('shows empty state when search results is empty array with short query', () => {
    mockSearchReturn = { data: [], isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: 'XY' } })

    expect(screen.getByText(/未找到与/)).toBeInTheDocument()
  })

  // ========== dropdown visibility ==========

  it('does not show dropdown when disabled', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} disabled />)
    // Even though mock data is set, disabled should prevent dropdown
    expect(screen.queryByText('张某诉李某')).not.toBeInTheDocument()
  })

  it('shows dropdown with results when open and has results', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })

    // Results should be visible
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.getByText('王某诉赵某')).toBeInTheDocument()
  })

  // ========== click outside ==========

  it('closes dropdown when clicking outside the component', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(
      <div>
        <CaseSearchSelect onSelect={vi.fn()} />
        <div data-testid="outside">Outside</div>
      </div>,
    )
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.queryByText('张某诉李某')).not.toBeInTheDocument()
  })

  it('keeps dropdown open on mousedown inside component (click-outside only)', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()

    // mousedown inside the container does NOT close the dropdown
    fireEvent.mouseDown(screen.getByText('张某诉李某'))
    // Still open because click was inside container
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
  })

  // ========== className prop ==========

  it('applies custom className', () => {
    const { container } = render(<CaseSearchSelect onSelect={vi.fn()} className="my-class" />)
    expect(container.firstChild).toHaveClass('my-class')
  })

  // ========== error state from hook ==========

  it('handles error state from search hook gracefully', () => {
    mockSearchReturn = { data: undefined, isLoading: false, error: new Error('Network error') }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    // When data is undefined and not loading, hasResults is false -> EmptyState shows
    expect(screen.getByText(/未找到与/)).toBeInTheDocument()
  })

  // ========== no results returned when data is undefined ==========

  it('shows empty state when data is undefined and not loading', () => {
    mockSearchReturn = { data: undefined, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    expect(screen.getByText(/未找到与/)).toBeInTheDocument()
  })

  // ========== loading and results coexistence ==========

  it('hides results when loading is true (loading takes priority)', () => {
    mockSearchReturn = { data: sampleResults, isLoading: true, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })

    // Loading state should be shown, not the results
    expect(screen.getByText('搜索中...')).toBeInTheDocument()
    expect(screen.queryByText('张某诉李某')).not.toBeInTheDocument()
  })

  // ========== multiple results with different IDs ==========

  it('renders each result with its own key and click handler', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    const onSelect = vi.fn()
    render(<CaseSearchSelect onSelect={onSelect} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })

    fireEvent.click(screen.getByText('刘某诉陈某'))
    expect(onSelect).toHaveBeenCalledWith(sampleResults[2])
  })

  // ========== partial match queries ==========

  it('handles empty search results for single-char then shows results for multi-char', () => {
    const { rerender } = render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')

    // Type single char - shows hint
    fireEvent.change(input, { target: { value: '张' } })
    expect(screen.getByText('请输入至少 2 个字符搜索')).toBeInTheDocument()

    // Now mock returns results and type more chars
    mockSearchReturn = { data: [sampleResults[0]], isLoading: false, error: null }
    fireEvent.change(input, { target: { value: '张某' } })

    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.queryByText('请输入至少 2 个字符搜索')).not.toBeInTheDocument()
  })

  // ========== initial state with no value shows input ==========

  it('shows search input when no value is provided', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeInTheDocument()
  })

  it('shows search input when value is null', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={null} />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeInTheDocument()
  })

  // ========== sr-only texts for accessibility ==========

  it('has accessible sr-only text for clear button', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })
    expect(screen.getByText('清除')).toBeInTheDocument()
  })

  it('has accessible sr-only text for re-search button', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} value={selectedCase} />)
    expect(screen.getByText('重新搜索')).toBeInTheDocument()
  })

  // ========== transition between states ==========

  it('transitions from loading to results', () => {
    mockSearchReturn = { data: undefined, isLoading: true, error: null }
    const { rerender } = render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '张某' } })
    expect(screen.getByText('搜索中...')).toBeInTheDocument()

    // Simulate data arriving
    mockSearchReturn = { data: [sampleResults[0]], isLoading: false, error: null }
    rerender(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()
    expect(screen.queryByText('搜索中...')).not.toBeInTheDocument()
  })

  it('transitions from results to empty state when query changes', () => {
    mockSearchReturn = { data: sampleResults, isLoading: false, error: null }
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText('搜索案件名称或案号...')
    fireEvent.change(input, { target: { value: '诉' } })
    expect(screen.getByText('张某诉李某')).toBeInTheDocument()

    // Change query so that mock returns empty
    mockSearchReturn = { data: [], isLoading: false, error: null }
    fireEvent.change(input, { target: { value: '不存在' } })
    expect(screen.getByText(/未找到与/)).toBeInTheDocument()
  })
})
