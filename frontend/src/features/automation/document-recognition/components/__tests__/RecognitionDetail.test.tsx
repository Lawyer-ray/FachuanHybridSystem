/**
 * RecognitionDetail Component Tests
 * 测试文书识别详情组件
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

const mockShouldPoll = vi.fn().mockReturnValue(false)

vi.mock('../../hooks/use-recognition-task', () => ({
  useRecognitionTask: vi.fn(),
  shouldPoll: (...args: unknown[]) => mockShouldPoll(...args),
}))

vi.mock('../../hooks/use-recognition-mutations', () => ({
  useUpdateRecognitionInfo: vi.fn(),
}))

vi.mock('../RecognitionResult', () => ({
  RecognitionResult: () => <div data-testid="recognition-result" />,
}))

vi.mock('../ManualBindingDialog', () => ({
  ManualBindingDialog: () => <div data-testid="manual-binding-dialog" />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
  CardContent: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
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
import { RecognitionDetail } from '../RecognitionDetail'
import { useRecognitionTask } from '../../hooks/use-recognition-task'
import { useUpdateRecognitionInfo } from '../../hooks/use-recognition-mutations'

const mockTask = {
  id: 1,
  file_name: '判决书.pdf',
  status: 'success',
  recognized_case_number: '(2026)沪01民初123号',
  recognized_court: '上海市第一中级人民法院',
  recognized_type: 'judgment',
  bound_case_id: 100,
  created_at: '2026-06-15T10:00:00Z',
  completed_at: '2026-06-15T10:05:00Z',
  error_message: null,
}

describe('RecognitionDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useUpdateRecognitionInfo).mockReturnValue({ mutate: vi.fn(), isPending: false } as any)
    mockShouldPoll.mockReturnValue(false)
  })

  it('renders loading skeleton when data is loading', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: undefined, isLoading: true } as any)
    render(<RecognitionDetail taskId={1} />)
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders task filename', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: mockTask, isLoading: false } as any)
    render(<RecognitionDetail taskId={1} />)
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
  })


  it('renders back button', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: mockTask, isLoading: false } as any)
    render(<RecognitionDetail taskId={1} />)
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('renders success status', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: mockTask, isLoading: false } as any)
    render(<RecognitionDetail taskId={1} />)
    expect(screen.getByText('成功')).toBeInTheDocument()
  })

  it('renders recognition result when status is success', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: mockTask, isLoading: false } as any)
    render(<RecognitionDetail taskId={1} />)
    expect(screen.getByTestId('recognition-result')).toBeInTheDocument()
  })

  it('renders processing state', () => {
    vi.mocked(useRecognitionTask).mockReturnValue({ data: { ...mockTask, status: 'processing' }, isLoading: false } as any)
    mockShouldPoll.mockReturnValue(true)
    render(<RecognitionDetail taskId={1} />)
    expect(screen.getByText('处理中')).toBeInTheDocument()
  })
})
