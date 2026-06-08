import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SupplementaryAgreementList } from '../SupplementaryAgreementList'
import { toast } from 'sonner'
import type { SupplementaryAgreement } from '../../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  Plus: () => <svg data-testid="plus-icon" />,
  Edit: () => <svg data-testid="edit-icon" />,
  Trash2: () => <svg data-testid="trash-icon" />,
  FileText: () => <svg data-testid="file-text-icon" />,
}))

const mockCreateMutateAsync = vi.fn()
const mockUpdateMutateAsync = vi.fn()
const mockDeleteMutateAsync = vi.fn()

vi.mock('../../hooks/use-agreement-mutations', () => ({
  useAgreementMutations: () => ({
    createAgreement: { mutateAsync: mockCreateMutateAsync, isPending: false },
    updateAgreement: { mutateAsync: mockUpdateMutateAsync, isPending: false },
    deleteAgreement: { mutateAsync: mockDeleteMutateAsync, isPending: false },
  }),
}))

vi.mock('../AgreementFormDialog', () => ({
  AgreementFormDialog: ({ open, onSubmit, agreement }: { open: boolean; onSubmit: (d: unknown) => void; agreement?: unknown }) => (
    open ? <div data-testid="form-dialog">
      <span>{agreement ? 'edit' : 'create'}</span>
      <button onClick={() => onSubmit({ contract_id: 1, name: 'Test' })}>Submit</button>
    </div> : null
  ),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  CardTitle: ({ children, className }: { children: React.ReactNode; className?: string }) => <h3 className={className}>{children}</h3>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: { children: React.ReactNode; variant?: string }) => <span data-variant={variant}>{children}</span>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

function makeAgreement(overrides: Partial<SupplementaryAgreement> = {}): SupplementaryAgreement {
  return {
    id: 1, contract: 1, name: 'Test Agreement', parties: [],
    created_at: '2025-06-01T00:00:00', updated_at: '2025-06-01T00:00:00', ...overrides,
  }
}

describe('SupplementaryAgreementList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('non-compact mode', () => {
    it('renders empty state', () => {
      render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
      expect(screen.getByText('暂无补充协议')).toBeInTheDocument()
    })

    it('renders agreements with name', () => {
      const agreements = [makeAgreement({ name: '补充协议 A' })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      expect(screen.getByText('补充协议 A')).toBeInTheDocument()
    })

    it('renders agreements with fallback name when name is null', () => {
      const agreements = [makeAgreement({ name: null })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      expect(screen.getByText('补充协议 #1')).toBeInTheDocument()
    })

    it('renders party badges', () => {
      const agreements = [makeAgreement({
        parties: [{ id: 1, client: 1, role: 'PRINCIPAL', client_detail: {} as any, client_name: '张三', is_our_client: true, role_label: '委托人' }],
      })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      expect(screen.getByText('张三 (委托人)')).toBeInTheDocument()
    })

    it('renders created date', () => {
      const agreements = [makeAgreement({ created_at: '2025-06-01T00:00:00' })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      expect(screen.getByText(/2025-06-01/)).toBeInTheDocument()
    })

    it('renders title with FileText icon', () => {
      render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
      expect(screen.getByText('补充协议')).toBeInTheDocument()
    })

    it('opens create dialog when clicking add', () => {
      render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
      fireEvent.click(screen.getByText('新增'))
      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
      expect(screen.getByText('create')).toBeInTheDocument()
    })

    it('opens edit dialog when clicking edit', () => {
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      fireEvent.click(screen.getByTestId('edit-icon').closest('button')!)
      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
      expect(screen.getByText('edit')).toBeInTheDocument()
    })

    it('opens delete dialog when clicking delete', () => {
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      fireEvent.click(screen.getByTestId('trash-icon').closest('button')!)
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })

    it('handles successful create', async () => {
      mockCreateMutateAsync.mockResolvedValue({})
      render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
      fireEvent.click(screen.getByText('新增'))
      fireEvent.click(screen.getByText('Submit'))
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('补充协议已添加'))
    })

    it('handles successful update', async () => {
      mockUpdateMutateAsync.mockResolvedValue({})
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      fireEvent.click(screen.getByTestId('edit-icon').closest('button')!)
      fireEvent.click(screen.getByText('Submit'))
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('补充协议已更新'))
    })

    it('handles create failure', async () => {
      mockCreateMutateAsync.mockRejectedValue(new Error('fail'))
      render(<SupplementaryAgreementList contractId={1} agreements={[]} />)
      fireEvent.click(screen.getByText('新增'))
      fireEvent.click(screen.getByText('Submit'))
      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('操作失败'))
    })

    it('handles successful delete', async () => {
      mockDeleteMutateAsync.mockResolvedValue({})
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      fireEvent.click(screen.getByTestId('trash-icon').closest('button')!)
      fireEvent.click(screen.getByText('删除'))
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('补充协议已删除'))
    })

    it('handles delete failure', async () => {
      mockDeleteMutateAsync.mockRejectedValue(new Error('fail'))
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} />)
      fireEvent.click(screen.getByTestId('trash-icon').closest('button')!)
      fireEvent.click(screen.getByText('删除'))
      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('删除失败'))
    })
  })

  describe('compact mode', () => {
    it('renders compact empty state', () => {
      render(<SupplementaryAgreementList contractId={1} agreements={[]} compact />)
      expect(screen.getByText('暂无补充协议')).toBeInTheDocument()
    })

    it('renders compact agreement list', () => {
      const agreements = [makeAgreement({ name: 'Compact Agreement' })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      expect(screen.getByText('Compact Agreement')).toBeInTheDocument()
    })

    it('renders compact agreement with fallback name', () => {
      const agreements = [makeAgreement({ name: null })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      expect(screen.getByText('补充协议 #1')).toBeInTheDocument()
    })

    it('renders compact party names', () => {
      const agreements = [makeAgreement({
        parties: [
          { id: 1, client: 1, role: 'PRINCIPAL', client_detail: {} as any, client_name: '李四', is_our_client: true, role_label: '委托人' },
          { id: 2, client: 2, role: 'BENEFICIARY', client_detail: {} as any, client_name: '王五', is_our_client: false, role_label: '受益人' },
        ],
      })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      expect(screen.getByText('李四、王五')).toBeInTheDocument()
    })

    it('renders compact date', () => {
      const agreements = [makeAgreement({ created_at: '2025-06-15T10:00:00' })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      expect(screen.getByText('2025-06-15')).toBeInTheDocument()
    })

    it('compact mode opens create dialog', () => {
      render(<SupplementaryAgreementList contractId={1} agreements={[]} compact />)
      fireEvent.click(screen.getByText('新增'))
      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
    })

    it('compact mode opens edit dialog', () => {
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      fireEvent.click(screen.getByTestId('edit-icon').closest('button')!)
      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
    })

    it('compact mode opens delete dialog', () => {
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      fireEvent.click(screen.getByTestId('trash-icon').closest('button')!)
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    })

    it('compact mode handles delete', async () => {
      mockDeleteMutateAsync.mockResolvedValue({})
      const agreements = [makeAgreement()]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      fireEvent.click(screen.getByTestId('trash-icon').closest('button')!)
      fireEvent.click(screen.getByText('删除'))
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('补充协议已删除'))
    })

    it('compact mode handles create', async () => {
      mockCreateMutateAsync.mockResolvedValue({})
      render(<SupplementaryAgreementList contractId={1} agreements={[]} compact />)
      fireEvent.click(screen.getByText('新增'))
      fireEvent.click(screen.getByText('Submit'))
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith('补充协议已添加'))
    })

    it('compact mode renders parties without content when empty', () => {
      const agreements = [makeAgreement({ parties: [] })]
      render(<SupplementaryAgreementList contractId={1} agreements={agreements} compact />)
      expect(screen.getByText('Test Agreement')).toBeInTheDocument()
    })
  })
})
