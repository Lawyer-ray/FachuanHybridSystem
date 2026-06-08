/**
 * CourierTrackingTool Component Tests
 * 测试快递查询工具组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: () => '2026-06-15',
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (url: string) => `http://localhost${url}`,
}))

vi.mock('../../hooks/use-express-tasks', () => ({
  useExpressTasks: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => <span className={className as string} data-variant={variant}>{children}</span>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) => <td className={className} colSpan={colSpan}>{children}</td>,
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

import { render, screen } from '@testing-library/react'
import { CourierTrackingTool } from '../CourierTrackingTool'
import { useExpressTasks } from '../../hooks/use-express-tasks'

const mockTasks = [
  {
    id: 1,
    title: '顺丰快递查询',
    carrier_type: 'sf',
    tracking_number: 'SF123456789',
    status: 'success',
    result_pdf: '/media/result.pdf',
    created_at: '2026-06-15T10:00:00Z',
  },
  {
    id: 2,
    title: 'EMS查询',
    carrier_type: 'ems',
    tracking_number: 'EM987654321',
    status: 'pending',
    result_pdf: null,
    created_at: '2026-06-15T11:00:00Z',
  },
]

describe('CourierTrackingTool', () => {
  it('renders page title and description', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByText('快递查询')).toBeInTheDocument()
    expect(screen.getByText('查询法律文书快递状态')).toBeInTheDocument()
  })

  it('renders add button', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByText('添加快递')).toBeInTheDocument()
  })

  it('renders empty state when no tasks', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByText('暂无查询任务')).toBeInTheDocument()
  })

  it('renders task rows when data is available', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: mockTasks, isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByText('顺丰速运')).toBeInTheDocument()
    expect(screen.getByText('EMS')).toBeInTheDocument()
    expect(screen.getByText('SF123456789')).toBeInTheDocument()
  })

  it('renders status badges', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: mockTasks, isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('待处理')).toBeInTheDocument()
  })

  it('renders PDF link for tasks with result', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: mockTasks, isLoading: false } as any)
    render(<CourierTrackingTool />)
    const pdfLink = screen.getByText('PDF')
    expect(pdfLink.closest('a')).toHaveAttribute('href', expect.stringContaining('/media/result.pdf'))
  })

  it('renders search input', () => {
    vi.mocked(useExpressTasks).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CourierTrackingTool />)
    expect(screen.getByPlaceholderText('输入快递单号...')).toBeInTheDocument()
  })
})
