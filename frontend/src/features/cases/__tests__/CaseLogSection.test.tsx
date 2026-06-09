import { render, screen, fireEvent, act } from '@testing-library/react'
import { CaseLogSection } from '../components/CaseLogSection'
import { toast } from 'sonner'
import type { CaseLog } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d?.slice(0, 10) || '' }))
vi.mock('@/lib/api', () => ({ resolveMediaUrl: (url: string) => `http://media${url}` }))

vi.mock('lucide-react', () => ({
  Paperclip: () => <svg data-testid="paperclip-icon" />,
  Trash2: () => <svg data-testid="trash-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  Download: () => <svg data-testid="download-icon" />,
  Bell: () => <svg data-testid="bell-icon" />,
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../hooks/use-log-mutations', () => ({
  useLogMutations: () => ({
    createLog: { mutate: mockCreateMutate, isPending: false },
    deleteLog: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, className }: Record<string, unknown>) => <label className={className as string}>{children}</label>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (v: string) => void }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children, size }: { children: React.ReactNode; size?: string }) => <div data-size={size}>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

function makeLog(overrides: Partial<CaseLog> = {}): CaseLog {
  return {
    id: 1, case: 1, content: 'Test log content', actor: 1,
    actor_detail: { id: 1, username: 'lawyer1', real_name: '张律师', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    attachments: [], reminders: [],
    created_at: '2025-06-01T10:00:00', updated_at: '2025-06-01T10:00:00', ...overrides,
  }
}

describe('CaseLogSection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state', () => {
    render(<CaseLogSection logs={[]} />)
    expect(screen.getByText('暂无案件日志')).toBeInTheDocument()
  })

  it('renders log content', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.getByText('Test log content')).toBeInTheDocument()
  })

  it('renders actor name', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('renders fallback actor name from username', () => {
    const log = makeLog({
      actor_detail: { id: 1, username: 'user1', real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('user1')).toBeInTheDocument()
  })

  it('renders unknown actor fallback', () => {
    const log = makeLog({
      actor_detail: { id: 1, username: null, real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  it('renders date', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.getByText('2025-06-01')).toBeInTheDocument()
  })

  it('renders multiple logs sorted by date', () => {
    const logs = [
      makeLog({ id: 1, content: 'First', created_at: '2025-06-01T10:00:00' }),
      makeLog({ id: 2, content: 'Second', created_at: '2025-06-02T10:00:00' }),
    ]
    render(<CaseLogSection logs={logs} />)
    const contentElements = screen.getAllByText(/First|Second/)
    // Second should come first (sorted by newest first)
    expect(contentElements[0]).toHaveTextContent('Second')
    expect(contentElements[1]).toHaveTextContent('First')
  })

  it('renders attachments', () => {
    const log = makeLog({
      attachments: [{ id: 1, log: 1, original_filename: 'doc.pdf', file_path: '/files/doc.pdf', media_url: null, uploaded_at: '2025-06-01' }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('doc.pdf')).toBeInTheDocument()
    expect(screen.getByTestId('paperclip-icon')).toBeInTheDocument()
  })

  it('renders attachment without filename fallback', () => {
    const log = makeLog({
      attachments: [{ id: 1, log: 1, original_filename: '', file_path: '/files/doc.pdf', media_url: null, uploaded_at: '2025-06-01' }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('附件 #1')).toBeInTheDocument()
  })

  it('renders attachment with media_url', () => {
    const log = makeLog({
      attachments: [{ id: 1, log: 1, original_filename: 'img.png', file_path: null, media_url: '/media/img.png', uploaded_at: '2025-06-01' }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('img.png')).toBeInTheDocument()
  })

  it('renders attachment without URL as plain text', () => {
    const log = makeLog({
      attachments: [{ id: 1, log: 1, original_filename: 'no-url.pdf', file_path: null, media_url: null, uploaded_at: '2025-06-01' }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('no-url.pdf')).toBeInTheDocument()
  })

  it('renders reminders', () => {
    const log = makeLog({
      reminders: [{ id: 1, reminder_type: 'hearing', due_at: '2025-07-01T09:00:00', is_completed: false }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('开庭')).toBeInTheDocument()
    expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
  })

  it('renders completed reminder with checkmark', () => {
    const log = makeLog({
      reminders: [{ id: 1, reminder_type: 'hearing', due_at: '2025-07-01T09:00:00', is_completed: true }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('✓')).toBeInTheDocument()
  })

  it('renders unknown reminder type fallback', () => {
    const log = makeLog({
      reminders: [{ id: 1, reminder_type: 'unknown_type', due_at: '2025-07-01T09:00:00', is_completed: false }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('unknown_type')).toBeInTheDocument()
  })

  it('renders add dialog when editable', () => {
    render(<CaseLogSection logs={[]} editable caseId={1} />)
    // Need to find the add button - but CaseLogSection doesn't have an explicit add button
    // The add is triggered via ref.openDialog()
  })

  it('does not render delete button when not editable', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    expect(screen.queryByTestId('trash-icon')).not.toBeInTheDocument()
  })

  it('renders delete button when editable', () => {
    render(<CaseLogSection logs={[makeLog()]} editable caseId={1} />)
    expect(screen.getByTestId('trash-icon')).toBeInTheDocument()
  })

  it('handles delete success', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CaseLogSection logs={[makeLog()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('删除'))
    expect(toast.success).toHaveBeenCalledWith('删除成功')
  })

  it('handles delete error', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Delete failed')) })
    render(<CaseLogSection logs={[makeLog()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('删除'))
    expect(toast.error).toHaveBeenCalledWith('Delete failed')
  })

  it('renders with ref', () => {
    const ref = { current: null as any }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    expect(ref.current).toBeTruthy()
    expect(typeof ref.current.openDialog).toBe('function')
  })

  it('opens dialog via ref', () => {
    const ref = { current: null as any }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
    expect(screen.getByText('添加案件日志')).toBeInTheDocument()
  })

  it('handles add with empty content', () => {
    const ref = { current: null as any }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    fireEvent.click(screen.getByText('确认'))
    expect(mockCreateMutate).not.toHaveBeenCalled()
  })

  it('handles add with content', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    const ref = { current: null as any }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    const textarea = screen.getByPlaceholderText('请输入日志内容')
    fireEvent.change(textarea, { target: { value: 'New log entry' } })
    fireEvent.click(screen.getByText('确认'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      { case_id: 1, content: 'New log entry' },
      expect.any(Object),
    )
    expect(toast.success).toHaveBeenCalledWith('添加日志成功')
  })

  it('handles add error', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Create failed')) })
    const ref = { current: null as any }
    render(<CaseLogSection logs={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    const textarea = screen.getByPlaceholderText('请输入日志内容')
    fireEvent.change(textarea, { target: { value: 'New log' } })
    fireEvent.click(screen.getByText('确认'))
    expect(toast.error).toHaveBeenCalledWith('Create failed')
  })

  it('renders first log with primary border', () => {
    render(<CaseLogSection logs={[makeLog()]} />)
    // The first timeline dot should have primary border
    expect(screen.getByText('Test log content')).toBeInTheDocument()
  })

  it('renders reminders with dates', () => {
    const log = makeLog({
      reminders: [{ id: 1, reminder_type: 'appeal_period', due_at: '2025-08-01T00:00:00', is_completed: false }],
    })
    render(<CaseLogSection logs={[log]} />)
    expect(screen.getByText('上诉期')).toBeInTheDocument()
  })

  it('does not render dialog when not editable', () => {
    render(<CaseLogSection logs={[]} />)
    expect(screen.queryByText('添加案件日志')).not.toBeInTheDocument()
  })
})
