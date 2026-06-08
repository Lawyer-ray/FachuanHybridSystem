import { render, screen, fireEvent, act } from '@testing-library/react'
import { CauseSelector } from '../components/CauseSelector'

vi.mock('lucide-react', () => ({
  Search: (props: Record<string, unknown>) => <svg data-testid="search-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
}))

vi.mock('../hooks/use-reference-data', () => ({
  useCauseSearch: vi.fn(() => ({ data: [], isLoading: false })),
}))

vi.mock('@/components/ui/input', () => ({
  Input: ({ ...props }: Record<string, unknown>) => <input data-testid="cause-input" {...props} />,
}))

import { useCauseSearch } from '../hooks/use-reference-data'
const mockUseCauseSearch = vi.mocked(useCauseSearch)

describe('CauseSelector', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockUseCauseSearch.mockReturnValue({ data: [], isLoading: false } as never)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders search input', () => {
    render(<CauseSelector value={null} onChange={vi.fn()} />)
    expect(screen.getByTestId('cause-input')).toBeInTheDocument()
  })

  it('renders with initial value', () => {
    render(<CauseSelector value="合同纠纷" onChange={vi.fn()} />)
    const input = screen.getByTestId('cause-input') as HTMLInputElement
    expect(input.value).toBe('合同纠纷')
  })

  it('shows loading indicator when searching', () => {
    mockUseCauseSearch.mockReturnValue({ data: [], isLoading: true } as never)
    render(<CauseSelector value={null} onChange={vi.fn()} />)
    expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
  })

  it('shows results when available', () => {
    mockUseCauseSearch.mockReturnValue({
      data: [{ id: 1, name: '合同纠纷' }, { id: 2, name: '借贷纠纷' }],
      isLoading: false,
    } as never)
    render(<CauseSelector value="纠" onChange={vi.fn()} />)
    const input = screen.getByTestId('cause-input')
    fireEvent.focus(input)
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
    expect(screen.getByText('借贷纠纷')).toBeInTheDocument()
  })

  it('calls onChange when selecting a result', () => {
    const onChange = vi.fn()
    mockUseCauseSearch.mockReturnValue({
      data: [{ id: 1, name: '合同纠纷' }],
      isLoading: false,
    } as never)
    render(<CauseSelector value="纠" onChange={onChange} />)
    const input = screen.getByTestId('cause-input')
    fireEvent.focus(input)
    fireEvent.click(screen.getByText('合同纠纷'))
    expect(onChange).toHaveBeenCalledWith('合同纠纷')
  })

  it('shows empty message when no results found', () => {
    mockUseCauseSearch.mockReturnValue({ data: [], isLoading: false } as never)
    render(<CauseSelector value="不存在" onChange={vi.fn()} />)
    const input = screen.getByTestId('cause-input')
    fireEvent.focus(input)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('未找到匹配案由')).toBeInTheDocument()
  })
})
