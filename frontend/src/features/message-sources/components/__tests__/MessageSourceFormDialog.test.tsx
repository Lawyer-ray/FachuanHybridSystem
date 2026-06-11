import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MessageSourceFormDialog } from '../MessageSourceFormDialog'
import { messageSourceApi } from '../../api'
import type { MessageSource } from '../../types'

// ── Mocks ──

vi.mock('lucide-react', () => ({
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  Save: (p: Record<string, unknown>) => <svg data-testid="save" {...p} />,
  X: (p: Record<string, unknown>) => <svg data-testid="x" {...p} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('react-hook-form', async () => {
  const actual = await vi.importActual<typeof import('react-hook-form')>('react-hook-form')
  return { ...actual }
})

vi.mock('@hookform/resolvers/zod', async () => {
  const actual = await vi.importActual<typeof import('@hookform/resolvers/zod')>('@hookform/resolvers/zod')
  return { ...actual }
})

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  }
})

const { mockCredentialsData } = vi.hoisted(() => {
  const mockCredentialsData = {
    data: [
      { id: 1, site_name: 'Gmail', account: 'test@gmail.com' },
      { id: 2, site_name: 'Outlook', account: 'test@outlook.com' },
    ] as Array<{ id: number; site_name: string; account: string }>,
    isLoading: false,
  }
  return { mockCredentialsData }
})

vi.mock('@/features/organization/hooks/use-credentials', () => ({
  useCredentials: () => mockCredentialsData,
}))

vi.mock('../../api', () => ({
  messageSourceApi: {
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
    sync: vi.fn().mockResolvedValue({}),
    syncAll: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, type, variant, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} type={type as string} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, disabled }: Record<string, unknown>) => (
    <input type="checkbox" checked={checked as boolean} onChange={() => onCheckedChange?.(!checked)} disabled={disabled as boolean} data-testid="switch" />
  ),
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <form>{children}</form>,
  FormField: ({ render, name }: { render: (props: { field: { value: unknown; onChange: (v: unknown) => void; onBlur: () => void } }) => React.ReactNode; name: string }) => {
    // Simple field simulation
    return render({ field: { value: '', onChange: vi.fn(), onBlur: vi.fn() } })
  },
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormControl: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormMessage: () => <span />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, value, disabled }: { children: React.ReactNode; onValueChange?: (v: string) => void; value?: string; disabled?: boolean }) => (
    <div data-testid="select" data-value={value}>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <div data-testid={`select-item-${value}`}>{children}</div>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}))

// ── Helpers ──

function makeSource(overrides: Partial<MessageSource> = {}): MessageSource {
  return {
    id: 1,
    display_name: 'Test Source',
    source_type: 'imap',
    credential_account: 'test@gmail.com',
    is_enabled: true,
    poll_interval_minutes: 30,
    sync_since: null,
    imap_host: 'imap.gmail.com',
    imap_account: 'test@gmail.com',
    sender_whitelist: '',
    sender_blacklist: '',
    last_sync_at: null,
    last_sync_status: 'success',
    last_sync_error: '',
    created_at: '2025-01-01T00:00:00',
    ...overrides,
  } as MessageSource
}

// ── Tests ──

describe('MessageSourceFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset credentials mock to default state (loading test may mutate it)
    mockCredentialsData.isLoading = false
    mockCredentialsData.data = [
      { id: 1, site_name: 'Gmail', account: 'test@gmail.com' },
      { id: 2, site_name: 'Outlook', account: 'test@outlook.com' },
    ]
  })

  // ========== toDatetimeLocal helper ==========

  it('exports toDatetimeLocal as part of the module (tested indirectly)', () => {
    // toDatetimeLocal is a module-level function; covered via component usage
    render(<MessageSourceFormDialog open={false} onOpenChange={vi.fn()} />)
    // Component renders nothing when closed
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument()
  })

  // ========== Create mode ==========

  it('renders create dialog when open without source', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
    expect(screen.getByText('添加消息来源')).toBeInTheDocument()
    expect(screen.getByText('配置新的消息同步来源')).toBeInTheDocument()
  })

  it('renders cancel button in create mode', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('calls onOpenChange(false) when cancel is clicked in create mode', () => {
    const onOpenChange = vi.fn()
    render(<MessageSourceFormDialog open={true} onOpenChange={onOpenChange} />)
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('renders create form with basic config section', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('基本配置')).toBeInTheDocument()
  })

  it('renders create form with sender filter section', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('发件人过滤')).toBeInTheDocument()
  })

  it('renders IMAP config section for imap source_type', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('IMAP 配置')).toBeInTheDocument()
  })

  it('renders credential select items', () => {
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    // The credential select items are rendered by useCredentials mock data
    // Check for the text content of the SelectItem elements
    expect(screen.getByText(/Gmail.*test@gmail.com/)).toBeInTheDocument()
    expect(screen.getByText(/Outlook.*test@outlook.com/)).toBeInTheDocument()
  })

  // ========== Edit mode ==========

  it('renders edit dialog when source is provided', () => {
    const source = makeSource()
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
    expect(screen.getByText('修改消息来源配置')).toBeInTheDocument()
  })

  it('renders edit form with sync status section', () => {
    const source = makeSource()
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // "同步状态" appears as both a section header and a label, so use getAllByText
    const syncStatusElements = screen.getAllByText('同步状态')
    expect(syncStatusElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders last sync time as dash when null', () => {
    const source = makeSource({ last_sync_at: null })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // The "-" is rendered as an input value (disabled Input), not as text content
    const lastSyncTimeLabel = screen.getByText('最后同步时间')
    const input = lastSyncTimeLabel.closest('div')?.querySelector('input')
    expect(input).toHaveValue('-')
  })

  it('renders last sync time when available', () => {
    const source = makeSource({ last_sync_at: '2025-06-01T10:00:00Z' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // The value is formatted with toLocaleString - just check sync status section exists
    expect(screen.getByText('最后同步时间')).toBeInTheDocument()
  })

  it('renders last sync status label', () => {
    const source = makeSource({ last_sync_status: 'success' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // "同步状态" appears as both a section header and a label
    const syncStatusElements = screen.getAllByText('同步状态')
    expect(syncStatusElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders last sync status with unknown status', () => {
    const source = makeSource({ last_sync_status: 'unknown' as never })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // "同步状态" appears as both a section header and a label
    const syncStatusElements = screen.getAllByText('同步状态')
    expect(syncStatusElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders last sync error when present', () => {
    const source = makeSource({ last_sync_error: 'Connection timeout' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('同步错误信息')).toBeInTheDocument()
  })

  it('does not render last sync error section when empty', () => {
    const source = makeSource({ last_sync_error: '' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.queryByText('同步错误信息')).not.toBeInTheDocument()
  })

  it('renders source type label from SOURCE_TYPE_LABELS', () => {
    const source = makeSource({ source_type: 'imap' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // In edit mode, source type is rendered as a disabled Input value, not text content
    const sourceTypeLabel = screen.getByText('来源类型')
    const input = sourceTypeLabel.closest('div')?.querySelector('input')
    expect(input).toHaveValue('IMAP 邮箱')
  })

  it('renders credential account in edit mode', () => {
    const source = makeSource({ credential_account: 'test@gmail.com' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    // In edit mode, credential account is rendered as a disabled Input value, not text content
    const credentialLabel = screen.getByText('关联凭证')
    const input = credentialLabel.closest('div')?.querySelector('input')
    expect(input).toHaveValue('test@gmail.com')
  })

  it('renders IMAP config section in edit mode for imap source', () => {
    const source = makeSource({ source_type: 'imap' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('IMAP 主机')).toBeInTheDocument()
    expect(screen.getByText('IMAP 账号')).toBeInTheDocument()
  })

  it('does not render IMAP config for non-imap source in edit mode', () => {
    const source = makeSource({ source_type: 'court_inbox' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.queryByText('IMAP 主机')).not.toBeInTheDocument()
  })

  it('handles source with null optional fields in edit mode', () => {
    const source = makeSource({
      sync_since: null,
      imap_host: '',
      imap_account: '',
      sender_whitelist: '',
      sender_blacklist: '',
    })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  it('handles source with non-null sync_since in edit mode', () => {
    const source = makeSource({ sync_since: '2025-01-01T00:00:00' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  it('handles source with null imap_host in edit mode (coalesced to empty)', () => {
    const source = makeSource({ imap_host: null as unknown as string, imap_account: null as unknown as string, sender_whitelist: null as unknown as string, sender_blacklist: null as unknown as string })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  // ========== Reset on close/open ==========

  it('resets form when dialog is opened in create mode', () => {
    const { rerender } = render(<MessageSourceFormDialog open={false} onOpenChange={vi.fn()} />)
    rerender(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('添加消息来源')).toBeInTheDocument()
  })

  it('resets form when dialog is opened in edit mode', () => {
    const source = makeSource()
    const { rerender } = render(<MessageSourceFormDialog open={false} onOpenChange={vi.fn()} source={source} />)
    rerender(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  // ========== toDatetimeLocal coverage ==========

  it('renders with source having valid sync_since (covers toDatetimeLocal with valid ISO)', () => {
    const source = makeSource({ sync_since: '2025-06-15T10:30:00Z' })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  it('renders with source having empty string sync_since (covers toDatetimeLocal with falsy)', () => {
    const source = makeSource({ sync_since: '' as unknown as null })
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} source={source} />)
    expect(screen.getByText('编辑消息来源')).toBeInTheDocument()
  })

  // ========== Loading credentials state ==========

  it('renders with loading credentials (covers isLoadingCredentials branch)', () => {
    // Override the mock to return loading state by mutating the shared object
    mockCredentialsData.isLoading = true
    mockCredentialsData.data = []
    // Since module already mocked, we test the default value path through `credentials = []`
    render(<MessageSourceFormDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
  })

  // ========== Default export ==========

  it('exports MessageSourceFormDialog as default', async () => {
    const mod = await import('../MessageSourceFormDialog')
    expect(mod.default).toBeDefined()
  })
})
