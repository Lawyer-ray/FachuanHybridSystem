vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CASES: '/admin/cases', ADMIN_CASE_NEW: '/admin/cases/new' },
}))

vi.mock('@/components/shared/PageFooter', () => ({
  PageFooter: ({ stats }: any) => <div data-testid="page-footer">{stats?.[0]?.value}</div>,
}))

vi.mock('../CaseFilters', () => ({
  CaseFilters: () => <div data-testid="case-filters" />,
}))

vi.mock('../CaseTable', () => ({
  CaseTable: ({ cases, isLoading }: any) => (
    <div data-testid="case-table">
      {isLoading ? 'loading' : `${cases.length} cases`}
    </div>
  ),
}))

vi.mock('../../hooks/use-cases', () => ({
  useCases: vi.fn(),
}))

vi.mock('../../hooks/use-case-search', () => ({
  useCaseSearch: vi.fn(),
}))

vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: (v: string) => v,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { useCases } from '../../hooks/use-cases'
import { useCaseSearch } from '../../hooks/use-case-search'
import { CaseList } from '../CaseList'

const mockUseCases = useCases as unknown as ReturnType<typeof vi.fn>
const mockUseCaseSearch = useCaseSearch as unknown as ReturnType<typeof vi.fn>

describe('CaseList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCases.mockReturnValue({ data: [], isLoading: false })
    mockUseCaseSearch.mockReturnValue({ data: [], isLoading: false })
  })

  it('renders search input', () => {
    render(<CaseList />)
    expect(screen.getByPlaceholderText('搜索案件名称/案号...')).toBeInTheDocument()
  })

  it('renders create button', () => {
    render(<CaseList />)
    expect(screen.getByText('新建案件')).toBeInTheDocument()
  })

  it('renders case table', () => {
    render(<CaseList />)
    expect(screen.getByTestId('case-table')).toBeInTheDocument()
  })

  it('renders page footer', () => {
    render(<CaseList />)
    expect(screen.getByTestId('page-footer')).toBeInTheDocument()
  })

  it('renders filters when not searching', () => {
    render(<CaseList />)
    expect(screen.getByTestId('case-filters')).toBeInTheDocument()
  })

  it('updates search value on input', () => {
    render(<CaseList />)
    const input = screen.getByPlaceholderText('搜索案件名称/案号...')
    fireEvent.change(input, { target: { value: '测试搜索' } })
    expect(input).toHaveValue('测试搜索')
  })

  it('shows clear button when search has value', () => {
    render(<CaseList />)
    const input = screen.getByPlaceholderText('搜索案件名称/案号...')
    fireEvent.change(input, { target: { value: 'test' } })
    expect(screen.getByText('清除搜索')).toBeInTheDocument()
  })

  it('clears search when clear button clicked', () => {
    render(<CaseList />)
    const input = screen.getByPlaceholderText('搜索案件名称/案号...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('清除搜索'))
    expect(input).toHaveValue('')
  })

  it('shows loading state', () => {
    mockUseCases.mockReturnValue({ data: undefined, isLoading: true })
    render(<CaseList />)
    expect(screen.getByText('loading')).toBeInTheDocument()
  })

  it('shows cases count', () => {
    mockUseCases.mockReturnValue({
      data: [{ id: 1, name: '案件1' }, { id: 2, name: '案件2' }],
      isLoading: false,
    })
    render(<CaseList />)
    expect(screen.getByText('2 cases')).toBeInTheDocument()
  })
})
