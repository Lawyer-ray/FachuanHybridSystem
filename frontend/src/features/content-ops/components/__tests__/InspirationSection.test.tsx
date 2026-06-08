/**
 * InspirationSection Component Tests
 * 测试 AI 法律灵感推荐组件
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('../../hooks/use-content-ops', () => ({
  useInspiration: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: () => ({
    get: () => ({
      json: vi.fn().mockResolvedValue({ models: [], default_model: '' }),
    }),
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className, onClick }: Record<string, unknown>) => (
    <div className={className as string} onClick={onClick as React.MouseEventHandler}>{children}</div>
  ),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => (
    <span className={className as string} data-variant={variant}>{children}</span>
  ),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ className }: { className: string }) => <div className={className} data-testid="skeleton" />,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/command', () => ({
  Command: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandInput: ({ placeholder }: { placeholder: string }) => <input placeholder={placeholder} />,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandItem: ({ children, onSelect }: { children: React.ReactNode; onSelect: () => void }) => <div onClick={onSelect}>{children}</div>,
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { InspirationSection } from '../InspirationSection'
import { useInspiration } from '../../hooks/use-content-ops'
import { useQuery } from '@tanstack/react-query'

const mockTopics = [
  { title: '竞业限制纠纷', description: '分析竞业限制条款的效力认定', suggested_keyword: '竞业限制' },
  { title: '劳动仲裁时效', description: '劳动争议仲裁时效的起算点', suggested_keyword: '仲裁时效' },
]

describe('InspirationSection', () => {
  const defaultProps = {
    onSelectTopic: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useQuery).mockReturnValue({ data: { models: [{ id: 'gpt-4o', name: 'GPT-4o' }], default_model: 'gpt-4o' } } as any)
  })

  it('renders section title', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: null, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText('AI 法律灵感')).toBeInTheDocument()
  })

  it('renders generate button', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: null, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText('AI 灵感推荐')).toBeInTheDocument()
  })

  it('renders empty prompt when no data', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: null, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText(/点击「AI 灵感推荐」/)).toBeInTheDocument()
  })

  it('renders loading skeletons when fetching', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: null, isFetching: true, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders topic cards when data is loaded', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: mockTopics, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText('竞业限制纠纷')).toBeInTheDocument()
    expect(screen.getByText('劳动仲裁时效')).toBeInTheDocument()
  })

  it('renders keyword badges', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: mockTopics, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText('竞业限制')).toBeInTheDocument()
    expect(screen.getByText('仲裁时效')).toBeInTheDocument()
  })

  it('calls onSelectTopic when card is clicked', () => {
    const onSelectTopic = vi.fn()
    vi.mocked(useInspiration).mockReturnValue({ data: mockTopics, isFetching: false, error: null, refetch: vi.fn() } as any)
    render(<InspirationSection onSelectTopic={onSelectTopic} />)
    fireEvent.click(screen.getByText('竞业限制纠纷').closest('[class]')!)
    expect(onSelectTopic).toHaveBeenCalledWith(mockTopics[0])
  })

  it('renders error state', () => {
    vi.mocked(useInspiration).mockReturnValue({ data: null, isFetching: false, error: 'Failed to fetch', refetch: vi.fn() } as any)
    render(<InspirationSection {...defaultProps} />)
    expect(screen.getByText('Failed to fetch')).toBeInTheDocument()
    expect(screen.getByText('重试')).toBeInTheDocument()
  })
})
