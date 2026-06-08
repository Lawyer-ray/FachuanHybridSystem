/**
 * HotTopicList Component Tests
 * 测试热门话题列表组件
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('../../hooks/use-content-ops', () => ({
  useHotTopics: vi.fn(),
  useRefreshHotTopics: vi.fn(),
}))

vi.mock('../../api', () => ({
  contentOpsApi: { translateTopics: vi.fn() },
}))

vi.mock('../../types', () => ({
  HOT_TOPIC_SOURCE_LABEL: { toutiao: '头条', baidu: '百度', douyin: '抖音' },
}))

vi.mock('./HotTopicCard', () => ({
  HotTopicCard: ({ topic }: { topic: { title: string } }) => <div data-testid="hot-topic-card">{topic.title}</div>,
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value: string }) => <button data-value={value}>{children}</button>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ className }: { className: string }) => <div className={className} data-testid="skeleton" />,
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { HotTopicList } from '../HotTopicList'
import { useHotTopics, useRefreshHotTopics } from '../../hooks/use-content-ops'

const mockTopics = [
  { title: '劳动法新规', source: 'toutiao', rank: 1, url: 'http://example.com', heat: 10000 },
  { title: 'AI法律应用', source: 'baidu', rank: 2, url: 'http://example.com/2', heat: 8000 },
]

describe('HotTopicList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useRefreshHotTopics).mockReturnValue({ mutate: vi.fn(), isPending: false } as any)
  })

  it('renders section title', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: [], isLoading: false, error: null } as any)
    render(<HotTopicList />)
    expect(screen.getByText('热门话题')).toBeInTheDocument()
  })

  it('renders source tabs', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: [], isLoading: false, error: null } as any)
    render(<HotTopicList />)
    expect(screen.getByText('全部')).toBeInTheDocument()
  })

  it('renders refresh button', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: [], isLoading: false, error: null } as any)
    render(<HotTopicList />)
    expect(screen.getByText('刷新')).toBeInTheDocument()
  })

  it('renders loading skeletons', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    render(<HotTopicList />)
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders topic cards when data is loaded', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: mockTopics, isLoading: false, error: null } as any)
    render(<HotTopicList />)
    expect(screen.getByText('劳动法新规')).toBeInTheDocument()
    expect(screen.getByText('AI法律应用')).toBeInTheDocument()
  })

  it('renders error state', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: undefined, isLoading: false, error: 'Network error' } as any)
    render(<HotTopicList />)
    expect(screen.getByText('获取热点话题失败')).toBeInTheDocument()
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  it('renders empty state when no topics', () => {
    vi.mocked(useHotTopics).mockReturnValue({ data: [], isLoading: false, error: null } as any)
    render(<HotTopicList />)
    expect(screen.getByText('暂无热点数据')).toBeInTheDocument()
  })
})
