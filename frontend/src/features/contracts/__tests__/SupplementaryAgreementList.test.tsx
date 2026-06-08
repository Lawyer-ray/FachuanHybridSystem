import { render, screen } from '@testing-library/react'
import { SupplementaryAgreementList } from '../components/SupplementaryAgreementList'

vi.mock('lucide-react', () => ({
  Plus: () => <svg data-testid="plus" />,
  Edit: () => <svg data-testid="edit" />,
  Trash2: () => <svg data-testid="trash" />,
  FileText: () => <svg data-testid="file-text" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('../hooks/use-agreement-mutations', () => ({
  useAgreementMutations: () => ({
    createAgreement: { mutateAsync: vi.fn(), isPending: false },
    updateAgreement: { mutateAsync: vi.fn(), isPending: false },
    deleteAgreement: { mutateAsync: vi.fn(), isPending: false },
  }),
}))

vi.mock('../components/AgreementFormDialog', () => ({
  AgreementFormDialog: () => <div data-testid="agreement-form-dialog" />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
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
}))

describe('SupplementaryAgreementList', () => {
  it('renders empty state in default mode', () => {
    render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
    expect(screen.getByText('暂无补充协议')).toBeInTheDocument()
  })

  it('renders title in default mode', () => {
    render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
    expect(screen.getByText('补充协议')).toBeInTheDocument()
  })

  it('renders add button', () => {
    render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
    expect(screen.getByText('新增')).toBeInTheDocument()
  })

  it('renders agreement names', () => {
    const agreements = [
      { id: 1, name: '补充协议一', parties: [], created_at: '2024-01-15T00:00:00Z' },
    ]
    render(<SupplementaryAgreementList contractId={1} agreements={agreements as never} />)
    expect(screen.getByText('补充协议一')).toBeInTheDocument()
  })

  it('renders compact mode', () => {
    render(<SupplementaryAgreementList contractId={1} agreements={[]} compact />)
    expect(screen.getByText('暂无补充协议')).toBeInTheDocument()
  })

  it('renders compact mode with agreements', () => {
    const agreements = [
      { id: 1, name: '协议A', parties: [], created_at: '2024-01-15T00:00:00Z' },
    ]
    render(<SupplementaryAgreementList contractId={1} agreements={agreements as never} compact />)
    expect(screen.getByText('协议A')).toBeInTheDocument()
  })
})
