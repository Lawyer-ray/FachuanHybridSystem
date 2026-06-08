import { render, screen } from '@testing-library/react'
import { CaseAccessGrantSection } from '../components/CaseAccessGrantSection'

vi.mock('lucide-react', () => ({
  UserPlus: (props: Record<string, unknown>) => <svg data-testid="user-plus" {...props} />,
  Trash2: (props: Record<string, unknown>) => <svg data-testid="trash-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  ShieldCheck: (props: Record<string, unknown>) => <svg data-testid="shield-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../hooks/use-access-grant-mutations', () => ({
  useAccessGrantMutations: () => ({
    createGrant: { mutate: vi.fn(), isPending: false },
    deleteGrant: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
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

const mockGrants = [
  {
    id: 1,
    grantee_detail: { real_name: '王律师', username: 'wang', phone: '00000000000' },
  },
  {
    id: 2,
    grantee_detail: { real_name: '', username: 'liuser', phone: null },
  },
]

describe('CaseAccessGrantSection', () => {
  it('renders empty state when no grants', () => {
    render(<CaseAccessGrantSection grants={[]} />)
    expect(screen.getByText('暂无额外授权')).toBeInTheDocument()
  })

  it('renders grant names', () => {
    render(<CaseAccessGrantSection grants={mockGrants as never} />)
    expect(screen.getByText('王律师')).toBeInTheDocument()
  })

  it('falls back to username when real_name is empty', () => {
    render(<CaseAccessGrantSection grants={mockGrants as never} />)
    expect(screen.getByText('liuser')).toBeInTheDocument()
  })

  it('shows phone when available', () => {
    render(<CaseAccessGrantSection grants={mockGrants as never} />)
    expect(screen.getByText('00000000000')).toBeInTheDocument()
  })

  it('shows add button when editable', () => {
    render(<CaseAccessGrantSection grants={[]} caseId={1} editable />)
    expect(screen.getByText('添加授权')).toBeInTheDocument()
  })

  it('does not show add button when not editable', () => {
    render(<CaseAccessGrantSection grants={[]} caseId={1} />)
    expect(screen.queryByText('添加授权')).not.toBeInTheDocument()
  })

  it('renders shield icons for grants', () => {
    render(<CaseAccessGrantSection grants={mockGrants as never} />)
    expect(screen.getAllByTestId('shield-icon').length).toBeGreaterThanOrEqual(2)
  })
})
