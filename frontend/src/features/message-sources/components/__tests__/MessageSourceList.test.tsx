vi.mock('../../hooks/use-message-sources', () => ({
  useMessageSources: vi.fn(),
}))

vi.mock('../../api', () => ({
  messageSourceApi: {
    sync: vi.fn().mockResolvedValue({ success: true }),
    syncAll: vi.fn().mockResolvedValue({ success: true }),
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('../../components/MessageSourceFormDialog', () => ({
  MessageSourceFormDialog: () => <div data-testid="form-dialog" />,
}))

vi.mock('@/components/shared/EmptyState', () => ({
  EmptyState: ({ title }: any) => <div data-testid="empty-state">{title}</div>,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  }
})

import { render, screen, fireEvent } from '@testing-library/react'
import { MessageSourceList } from '../MessageSourceList'
import { useMessageSources } from '../../hooks/use-message-sources'

const mockUseMessageSources = vi.mocked(useMessageSources)

const mockSource = (overrides = {}) => ({
  id: 1, display_name: 'Court Email', source_type: 'imap',
  credential_account: 'court@example.com', poll_interval_minutes: 30,
  is_enabled: true, last_sync_at: '2026-06-01T12:00:00Z', last_sync_status: 'success',
  ...overrides,
})

describe('MessageSourceList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when no sources', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('暂无消息来源')).toBeInTheDocument()
  })

  it('renders table with source data', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('Court Email')).toBeInTheDocument()
    expect(screen.getByText('court@example.com')).toBeInTheDocument()
  })

  it('renders header buttons', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('全部同步')).toBeInTheDocument()
    expect(screen.getByText('添加来源')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    mockUseMessageSources.mockReturnValue({ data: undefined, isLoading: true } as any)
    const { container } = render(<MessageSourceList />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders multiple sources in table', () => {
    mockUseMessageSources.mockReturnValue({
      data: [
        mockSource({ id: 1, display_name: 'Source A' }),
        mockSource({ id: 2, display_name: 'Source B', source_type: 'yzw', is_enabled: false }),
      ],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('Source A')).toBeInTheDocument()
    expect(screen.getByText('Source B')).toBeInTheDocument()
  })

  it('renders sync button for each source', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步')).toBeInTheDocument()
  })

  it('renders disabled state when source is disabled', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: false })], isLoading: false } as any)
    render(<MessageSourceList />)
    // Disabled source shows PowerOff icon and "点击启用" title
    expect(screen.getByTitle('点击启用')).toBeInTheDocument()
  })

  it('renders enabled state when source is enabled', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: true })], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByTitle('点击禁用')).toBeInTheDocument()
  })

  it('renders last sync status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步成功')).toBeInTheDocument()
  })

  it('renders failed sync status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ last_sync_status: 'failed' })], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步失败')).toBeInTheDocument()
  })

  it('renders never synced status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ last_sync_at: null, last_sync_status: null })], isLoading: false } as any)
    render(<MessageSourceList />)
    // When last_sync_at is null, shows '-'
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders poll interval', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('30 分钟')).toBeInTheDocument()
  })

  it('renders different source types', () => {
    mockUseMessageSources.mockReturnValue({
      data: [mockSource({ source_type: 'yzw', display_name: 'YZW Source' })],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('YZW Source')).toBeInTheDocument()
  })

  it('renders source type badges', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('IMAP 邮箱')).toBeInTheDocument()
  })

  it('renders delete and edit actions', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getAllByText('编辑').length).toBeGreaterThanOrEqual(1)
    // Delete button uses icon only, check for button presence
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(5)
  })

  it('handles sync click', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('同步'))
  })

  it('handles sync all click', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('全部同步'))
  })

  it('handles add source click', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('添加来源'))
    expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
  })

  it('renders with no last sync time', () => {
    mockUseMessageSources.mockReturnValue({
      data: [mockSource({ last_sync_at: null })],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('显示名称')).toBeInTheDocument()
    expect(screen.getByText('来源类型')).toBeInTheDocument()
    expect(screen.getByText('同步状态')).toBeInTheDocument()
  })
})
