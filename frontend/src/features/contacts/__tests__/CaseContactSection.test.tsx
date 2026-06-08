import { render, screen } from '@testing-library/react'
import { CaseContactSection } from '../components/CaseContactSection'

vi.mock('lucide-react', () => ({
  Trash2: () => <svg data-testid="trash" />,
  Loader2: () => <svg data-testid="loader" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../hooks/use-contact-mutations', () => ({
  useContactMutations: () => ({
    createContact: { mutate: vi.fn(), isPending: false },
    deleteContact: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/features/cases/types', () => ({
  CASE_STAGE_LABELS: { first_instance: { zh: '一审' } },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
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

vi.mock('../types', () => ({
  CONTACT_ROLE_LABELS: {
    judge: { zh: '法官' },
    clerk: { zh: '书记员' },
  },
}))

describe('CaseContactSection', () => {
  it('renders empty state when no contacts', () => {
    render(<CaseContactSection contacts={[]} />)
    expect(screen.getByText('暂无工作人员信息')).toBeInTheDocument()
  })

  it('renders contact name', () => {
    const contacts = [{
      id: 1,
      name: '王法官',
      role: 'judge',
      role_display: '法官',
      phone: '010-12345678',
    }]
    render(<CaseContactSection contacts={contacts as never} />)
    expect(screen.getByText('王法官')).toBeInTheDocument()
  })

  it('renders contact phone', () => {
    const contacts = [{
      id: 1,
      name: '王法官',
      role: 'judge',
      phone: '010-12345678',
    }]
    render(<CaseContactSection contacts={contacts as never} />)
    expect(screen.getByText('010-12345678')).toBeInTheDocument()
  })

  it('renders add dialog title when open', () => {
    render(<CaseContactSection contacts={[]} caseId={1} editable />)
    // Dialog is always rendered but not visible by default
    expect(screen.getByText('添加工作人员')).toBeInTheDocument()
  })

  it('renders role display', () => {
    const contacts = [{
      id: 1,
      name: '王法官',
      role: 'judge',
      role_display: '法官',
    }]
    render(<CaseContactSection contacts={contacts as never} />)
    expect(screen.getAllByText('法官').length).toBeGreaterThanOrEqual(1)
  })
})
