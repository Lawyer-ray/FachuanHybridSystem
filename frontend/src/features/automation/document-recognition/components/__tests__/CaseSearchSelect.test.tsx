import { render, screen } from '@testing-library/react'
import { CaseSearchSelect } from '../CaseSearchSelect'

vi.mock('@/features/automation/document-recognition/hooks/use-case-search', () => ({
  useCaseSearch: vi.fn(() => ({
    data: undefined,
    isLoading: false,
  })),
}))

describe('CaseSearchSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders search input with default placeholder', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeInTheDocument()
  })

  it('renders custom placeholder', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} placeholder="选择案件..." />)
    expect(screen.getByPlaceholderText('选择案件...')).toBeInTheDocument()
  })

  it('renders selected case name and number', () => {
    const value = { id: 1, name: 'Test Case', case_number: '(2026)京01民初123号' }
    render(<CaseSearchSelect onSelect={vi.fn()} value={value as any} />)
    expect(screen.getByText('Test Case')).toBeInTheDocument()
    expect(screen.getByText('(2026)京01民初123号')).toBeInTheDocument()
  })

  it('is disabled when disabled prop is true', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} disabled />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeDisabled()
  })

  it('renders without value when no case selected', () => {
    render(<CaseSearchSelect onSelect={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索案件名称或案号...')).toBeInTheDocument()
  })
})
