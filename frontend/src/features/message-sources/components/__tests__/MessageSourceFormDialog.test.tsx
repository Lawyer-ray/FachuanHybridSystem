vi.mock('../api', () => ({
  messageSourceApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
  },
}))

vi.mock('@/features/organization/hooks/use-credentials', () => ({
  useCredentials: () => ({
    data: [
      { id: 1, site_name: 'Test Site', account: 'test@example.com' },
    ],
    isLoading: false,
  }),
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
import { MessageSourceFormDialog } from '../MessageSourceFormDialog'

describe('MessageSourceFormDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders create dialog title when no source provided', () => {
    render(<MessageSourceFormDialog {...defaultProps} />)
    expect(screen.getByText('添加消息来源')).toBeInTheDocument()
  })

  it('renders edit dialog title when source is provided', () => {
    const source = {
      id: 1,
      display_name: 'Test Source',
      source_type: 'imap',
      credential_id: 1,
      credential_account: 'test@example.com',
      poll_interval_minutes: 30,
      is_enabled: true,
      last_sync_at: null,
      last_sync_status: null,
      last_sync_error: null,
      sync_since: null,
      imap_host: null,
      imap_account: null,
      sender_whitelist: null,
      sender_blacklist: null,
    } as any
    render(<MessageSourceFormDialog {...defaultProps} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    const { container } = render(<MessageSourceFormDialog {...defaultProps} open={false} />)
    expect(container.textContent).not.toContain('添加消息来源')
  })

  it('renders form description for create mode', () => {
    render(<MessageSourceFormDialog {...defaultProps} />)
    expect(screen.getByText('配置新的消息同步来源')).toBeInTheDocument()
  })

  it('renders form description for edit mode', () => {
    const source = {
      id: 1, display_name: 'Test', source_type: 'imap',
      credential_id: 1, credential_account: 'test@example.com',
      poll_interval_minutes: 30, is_enabled: true,
      last_sync_at: null, last_sync_status: null, last_sync_error: null,
      sync_since: null, imap_host: null, imap_account: null,
      sender_whitelist: null, sender_blacklist: null,
    } as any
    render(<MessageSourceFormDialog {...defaultProps} source={source} />)
    expect(screen.getByText('修改消息来源配置')).toBeInTheDocument()
  })
})
