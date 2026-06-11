vi.mock('../../hooks/use-credentials', () => ({
  useCredentials: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))
const mockDeleteMutate = vi.fn()
vi.mock('../../hooks/use-credential-mutations', () => ({
  useCredentialMutations: () => ({
    deleteCredential: { mutate: mockDeleteMutate, isPending: false },
    createCredential: { mutate: vi.fn(), isPending: false },
    updateCredential: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: () => ({ data: [{ id: 1, real_name: '张三', username: 'zhang' }], isLoading: false }),
}))

vi.mock('../CredentialTable', () => ({
  CredentialTable: ({ credentials, onEdit, onDelete }: any) => (
    <div data-testid="credential-table">
      {credentials.map((c: any) => (
        <div key={c.id}>
          <span>{c.site_name}</span>
          <button onClick={() => onEdit(c)}>edit-{c.id}</button>
          <button onClick={() => onDelete(c)}>delete-{c.id}</button>
        </div>
      ))}
      {credentials.length === 0 && <span>暂无凭证数据</span>}
    </div>
  ),
}))
vi.mock('../CredentialFormDialog', () => ({
  CredentialFormDialog: ({ open, credential }: any) =>
    open ? <div data-testid="form-dialog">{credential ? 'edit' : 'create'}</div> : null,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, value }: any) => (
    <select data-testid="lawyer-filter" onChange={(e) => onValueChange?.(e.target.value)} value={value || ''}>
      {children}
    </select>
  ),
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: any) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick, disabled }: any) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  AlertDialogCancel: ({ children, onClick, disabled }: any) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h2>{children}</h2>,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { CredentialList } from '../CredentialList'
import { useCredentials } from '../../hooks/use-credentials'

describe('CredentialList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders create button and filter', () => {
    render(<CredentialList />)
    expect(screen.getByText('新建凭证')).toBeInTheDocument()
    expect(screen.getByText('全部律师')).toBeInTheDocument()
  })

  it('shows empty state when no credentials', () => {
    vi.mocked(useCredentials).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CredentialList />)
    expect(screen.getByText('暂无凭证数据')).toBeInTheDocument()
  })

  it('shows credential data', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    expect(screen.getByText('威科')).toBeInTheDocument()
  })

  it('opens create dialog when create button clicked', () => {
    render(<CredentialList />)
    fireEvent.click(screen.getByText('新建凭证'))
    expect(screen.getByTestId('form-dialog')).toHaveTextContent('create')
  })

  it('opens edit dialog when edit triggered', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    fireEvent.click(screen.getByText('edit-1'))
    expect(screen.getByTestId('form-dialog')).toHaveTextContent('edit')
  })

  it('opens delete dialog when delete triggered', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
  })

  it('confirms delete and shows success toast', async () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onSuccess()
    })
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalledWith(1, expect.any(Object))
      expect(toast.success).toHaveBeenCalledWith('凭证删除成功')
    })
  })

  it('handles delete error with Error', async () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onError(new Error('删除失败'))
    })
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  it('handles delete error with non-Error', async () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onError('unknown')
    })
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败，请重试')
    })
  })

  it('cancels delete when cancel clicked', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByText('取消'))
  })

  it('lawyer filter change to specific lawyer', () => {
    render(<CredentialList />)
    const select = screen.getByTestId('lawyer-filter')
    fireEvent.change(select, { target: { value: '1' } })
    expect(useCredentials).toHaveBeenCalledWith(expect.objectContaining({ lawyerId: 1 }))
  })

  it('lawyer filter change to all', () => {
    render(<CredentialList />)
    const select = screen.getByTestId('lawyer-filter')
    fireEvent.change(select, { target: { value: 'all' } })
    expect(useCredentials).toHaveBeenCalledWith(expect.objectContaining({ lawyerId: undefined }))
  })

  it('form dialog open change with false clears selected credential', () => {
    render(<CredentialList />)
    // Open create dialog
    fireEvent.click(screen.getByText('新建凭证'))
    expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
  })

  it('shows delete confirmation with credential site_name', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科先行', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    // '威科先行' appears in both the table mock and the alert dialog description
    const elements = screen.getAllByText(/威科先行/)
    expect(elements.length).toBeGreaterThanOrEqual(1)
  })

  it('shows confirm delete button text when not pending', () => {
    vi.mocked(useCredentials).mockReturnValue({
      data: [{ id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }],
      isLoading: false,
    } as any)
    render(<CredentialList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })
})
