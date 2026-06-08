import { render, screen } from '@testing-library/react'
import { CaseLogSection } from '../components/CaseLogSection'

vi.mock('lucide-react', () => ({
  Paperclip: (props: Record<string, unknown>) => <svg data-testid="paperclip" {...props} />,
  Trash2: (props: Record<string, unknown>) => <svg data-testid="trash-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  Download: (props: Record<string, unknown>) => <svg data-testid="download-icon" {...props} />,
  Bell: (props: Record<string, unknown>) => <svg data-testid="bell-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/date', () => ({
  formatDate: (d: string) => d,
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (url: string) => url,
}))

vi.mock('../hooks/use-log-mutations', () => ({
  useLogMutations: () => ({
    createLog: { mutate: vi.fn(), isPending: false },
    deleteLog: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const mockLogs = [
  {
    id: 1,
    content: '第一次开庭',
    created_at: '2024-01-15T10:00:00Z',
    actor_detail: { real_name: '张律师', username: 'zhang' },
    attachments: [],
    reminders: [],
  },
  {
    id: 2,
    content: '提交补充证据',
    created_at: '2024-01-20T14:00:00Z',
    actor_detail: { real_name: null, username: 'liuser' },
    attachments: [{ id: 10, original_filename: '证据.pdf', media_url: '/files/evidence.pdf', file_path: '' }],
    reminders: [{ id: 20, reminder_type: 'hearing', due_at: '2024-02-01T09:00:00Z', is_completed: false }],
  },
]

describe('CaseLogSection', () => {
  it('renders empty state when no logs', () => {
    render(<CaseLogSection logs={[]} />)
    expect(screen.getByText('暂无案件日志')).toBeInTheDocument()
  })

  it('renders log contents', () => {
    render(<CaseLogSection logs={mockLogs as never} />)
    expect(screen.getByText('第一次开庭')).toBeInTheDocument()
    expect(screen.getByText('提交补充证据')).toBeInTheDocument()
  })

  it('renders actor names', () => {
    render(<CaseLogSection logs={mockLogs as never} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
    expect(screen.getByText('liuser')).toBeInTheDocument()
  })

  it('renders attachment filenames', () => {
    render(<CaseLogSection logs={mockLogs as never} />)
    expect(screen.getByText('证据.pdf')).toBeInTheDocument()
  })

  it('renders reminder badges', () => {
    render(<CaseLogSection logs={mockLogs as never} />)
    expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
  })

  it('exposes openDialog via ref when editable', () => {
    const ref = { current: null as { openDialog: () => void } | null }
    render(<CaseLogSection logs={[]} caseId={1} editable ref={(r) => { ref.current = r }} />)
    expect(ref.current).toBeTruthy()
    expect(typeof ref.current!.openDialog).toBe('function')
  })

  it('does not show empty text when logs exist', () => {
    render(<CaseLogSection logs={mockLogs as never} />)
    expect(screen.queryByText('暂无案件日志')).not.toBeInTheDocument()
  })
})
