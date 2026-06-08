/**
 * RecognitionList Component Tests
 * 测试文书识别任务列表组件
 */

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: () => '2026-06-15',
}))

vi.mock('../../hooks/use-recognition-tasks', () => ({
  useRecognitionTasks: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-value={value}>{children}</div>,
  SelectTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder: string }) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, className }: { children: React.ReactNode; className?: string }) => <table className={className}>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) => <td className={className} colSpan={colSpan}>{children}</td>,
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children, onClick, className }: { children: React.ReactNode; onClick?: () => void; className?: string }) => <tr onClick={onClick} className={className}>{children}</tr>,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ className }: { className: string }) => <div className={className} data-testid="skeleton" />,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => (
    <span className={className as string} data-variant={variant}>{children}</span>
  ),
}))

import { render, screen } from '@testing-library/react'
import { RecognitionList } from '../RecognitionList'
import { useRecognitionTasks } from '../../hooks/use-recognition-tasks'

const mockTasks = [
  {
    id: 1,
    original_filename: '判决书.pdf',
    status: 'success',
    recognized_case_number: '(2026)沪01民初123号',
    bound_case_id: 100,
    created_at: '2026-06-15T10:00:00Z',
  },
  {
    id: 2,
    original_filename: '起诉状.docx',
    status: 'pending',
    recognized_case_number: null,
    bound_case_id: null,
    created_at: '2026-06-15T11:00:00Z',
  },
]

describe('RecognitionList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders upload button when callback provided', () => {
    vi.mocked(useRecognitionTasks).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<RecognitionList onUploadClick={vi.fn()} />)
    const uploadButtons = screen.getAllByText('上传文书'); expect(uploadButtons.length).toBeGreaterThan(0)
  })

  it('renders status filter', () => {
    vi.mocked(useRecognitionTasks).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<RecognitionList />)
    expect(screen.getByText('全部状态')).toBeInTheDocument()
  })

  it('renders loading skeletons when loading', () => {
    vi.mocked(useRecognitionTasks).mockReturnValue({ data: undefined, isLoading: true, isFetching: true } as any)
    render(<RecognitionList />)
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders empty state when no tasks', () => {
    vi.mocked(useRecognitionTasks).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<RecognitionList />)
    expect(screen.getByText('暂无识别任务')).toBeInTheDocument()
  })


})
