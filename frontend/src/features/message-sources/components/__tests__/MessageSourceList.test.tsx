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

import { render, screen } from '@testing-library/react'
import { MessageSourceList } from '../MessageSourceList'
import { useMessageSources } from '../../hooks/use-message-sources'

const mockUseMessageSources = vi.mocked(useMessageSources)

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
    mockUseMessageSources.mockReturnValue({
      data: [{
        id: 1, display_name: 'Court Email', source_type: 'imap',
        credential_account: 'court@example.com', poll_interval_minutes: 30,
        is_enabled: true, last_sync_at: '2026-06-01T12:00:00Z', last_sync_status: 'success',
      }],
      isLoading: false,
    } as any)
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
        { id: 1, display_name: 'Source A', source_type: 'imap', credential_account: 'source_a@placeholder.test', poll_interval_minutes: 30, is_enabled: true, last_sync_at: null, last_sync_status: null },
        { id: 2, display_name: 'Source B', source_type: 'yzw', credential_account: 'source_b@placeholder.test', poll_interval_minutes: 60, is_enabled: false, last_sync_at: null, last_sync_status: null },
      ],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('Source A')).toBeInTheDocument()
    expect(screen.getByText('Source B')).toBeInTheDocument()
  })
})
