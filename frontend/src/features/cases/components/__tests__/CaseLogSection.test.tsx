import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react'
import { CaseLogSection, type CaseLogSectionRef } from '../CaseLogSection'
import type { CaseLog } from '../../types'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../../hooks/use-log-mutations', () => ({
  useLogMutations: () => ({
    createLog: { mutate: mockCreateMutate, isPending: false },
    deleteLog: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/lib/date', () => ({
  formatDate: (v: string | null) => v ?? '-',
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    resolveMediaUrl: (url: string | null) => (url ? `http://backend${url}` : null),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open === false ? null : <div data-testid="dialog">{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('lucide-react', () => ({
  Paperclip: (p: Record<string, unknown>) => <svg data-testid="paperclip" {...p} />,
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  Download: (p: Record<string, unknown>) => <svg data-testid="download" {...p} />,
  Bell: (p: Record<string, unknown>) => <svg data-testid="bell" {...p} />,
}))

const makeLog = (overrides: Partial<CaseLog> = {}): CaseLog =>
  ({
    id: 1,
    content: '测试日志内容',
    created_at: '2025-01-15T10:00:00Z',
    actor_detail: { real_name: '张律师', username: 'zhang' },
    attachments: [],
    reminders: [],
    ...overrides,
  }) as unknown as CaseLog

describe('CaseLogSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // -- Rendering --

  it('shows empty message when no logs', () => {
    render(<CaseLogSection logs={[]} />)
    expect(screen.getByText('暂无案件日志')).toBeInTheDocument()
  })

  it('renders log content and actor name', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.getByText('测试日志内容')).toBeInTheDocument()
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('sorts logs by created_at descending (newest first)', () => {
    const logs = [
      makeLog({ id: 1, content: '老日志', created_at: '2025-01-01T10:00:00Z' }),
      makeLog({ id: 2, content: '新日志', created_at: '2025-06-01T10:00:00Z' }),
    ]
    render(<CaseLogSection logs={logs as any} />)
    const items = screen.getAllByText(/日志/)
    // "新日志" should appear before "老日志"
    expect(items[0].textContent).toContain('新日志')
  })

  it('uses username fallback when real_name is null', () => {
    render(<CaseLogSection logs={[makeLog({ actor_detail: { real_name: null, username: 'user1' } })]} />)
    expect(screen.getByText('user1')).toBeInTheDocument()
  })

  it('shows "未知" when both names are null', () => {
    render(<CaseLogSection logs={[makeLog({ actor_detail: null })]} />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  // -- Editable mode --

  it('shows delete button in editable mode with caseId', () => {
    render(<CaseLogSection logs={[makeLog()]} editable caseId={1} />)
    expect(screen.getByTestId('trash')).toBeInTheDocument()
  })

  it('does not show delete button when not editable', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.queryByTestId('trash')).not.toBeInTheDocument()
  })

  // -- Ref API --

  it('exposes openDialog via ref', () => {
    const ref = { current: null as CaseLogSectionRef | null }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(typeof ref.current!.openDialog).toBe('function')
  })

  it('opens add dialog via ref.openDialog', () => {
    const ref = { current: null as CaseLogSectionRef | null }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current!.openDialog() })
    expect(screen.getByText('添加案件日志')).toBeInTheDocument()
  })

  // -- Add dialog --

  it('renders dialog when editable with caseId', () => {
    const ref = { current: null as CaseLogSectionRef | null }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    // Open the dialog via ref
    act(() => { ref.current!.openDialog() })
    expect(screen.getByText('日志内容')).toBeInTheDocument()
  })

  it('does not render dialog when not editable', () => {
    render(<CaseLogSection logs={[]} />)
    expect(screen.queryByText('日志内容')).not.toBeInTheDocument()
  })

  it('does not render dialog when caseId is missing', () => {
    render(<CaseLogSection logs={[]} editable />)
    expect(screen.queryByText('日志内容')).not.toBeInTheDocument()
  })

  // -- Reminders --

  it('renders reminder badges', () => {
    const log = makeLog({
      reminders: [{
        id: 1,
        reminder_type: 'hearing',
        due_at: '2025-03-01T09:00:00Z',
        is_completed: false,
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByTestId('bell')).toBeInTheDocument()
  })

  it('renders completed reminder with checkmark', () => {
    const log = makeLog({
      reminders: [{
        id: 1,
        reminder_type: 'deadline',
        due_at: '2025-03-01T09:00:00Z',
        is_completed: true,
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByText('✓')).toBeInTheDocument()
  })

  // -- Attachments --

  it('renders attachment links with url', () => {
    const log = makeLog({
      attachments: [{
        id: 1,
        original_filename: '证据.pdf',
        media_url: '/media/evidence.pdf',
        file_path: null,
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByText('证据.pdf')).toBeInTheDocument()
    expect(screen.getByTestId('paperclip')).toBeInTheDocument()
  })

  it('renders attachment with file_path when media_url is null', () => {
    const log = makeLog({
      attachments: [{
        id: 2,
        original_filename: '文件.doc',
        media_url: null,
        file_path: '/files/doc.doc',
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByText('文件.doc')).toBeInTheDocument()
  })

  it('renders attachment with fallback display name', () => {
    const log = makeLog({
      attachments: [{
        id: 3,
        original_filename: '',
        media_url: '/media/3',
        file_path: null,
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByText('附件 #3')).toBeInTheDocument()
  })

  it('renders attachment without link when no url', () => {
    const log = makeLog({
      attachments: [{
        id: 4,
        original_filename: 'no-url.pdf',
        media_url: null,
        file_path: null,
      }],
    })
    render(<CaseLogSection logs={[log as any]} />)
    expect(screen.getByText('no-url.pdf')).toBeInTheDocument()
  })

  // -- Delete --

  it('calls deleteLog.mutate on delete', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    render(<CaseLogSection logs={[makeLog()]} editable caseId={1} />)
    const deleteButtons = screen.getAllByText('删除')
    fireEvent.click(deleteButtons[deleteButtons.length - 1])
    expect(mockDeleteMutate).toHaveBeenCalledWith(1, expect.objectContaining({
      onSuccess: expect.any(Function),
      onError: expect.any(Function),
    }))
  })

  // -- Multiple logs with timeline --

  it('renders multiple logs with timeline', () => {
    const logs = [
      makeLog({ id: 1, content: '第一条', created_at: '2025-01-01T10:00:00Z' }),
      makeLog({ id: 2, content: '第二条', created_at: '2025-06-01T10:00:00Z' }),
    ]
    render(<CaseLogSection logs={logs as any} />)
    expect(screen.getByText('第一条')).toBeInTheDocument()
    expect(screen.getByText('第二条')).toBeInTheDocument()
  })

  it('highlights first log with primary border', () => {
    const logs = [
      makeLog({ id: 1, content: '最新日志', created_at: '2025-06-01T10:00:00Z' }),
      makeLog({ id: 2, content: '旧日志', created_at: '2025-01-01T10:00:00Z' }),
    ]
    render(<CaseLogSection logs={logs as any} />)
    // The first rendered log (sorted newest first) has border-primary
    const primaryDots = document.querySelectorAll('.border-primary')
    expect(primaryDots.length).toBeGreaterThan(0)
  })

  // -- Default export --

  it('has a default export', async () => {
    const mod = await import('../CaseLogSection')
    expect(mod.default).toBe(mod.CaseLogSection)
  })
})
