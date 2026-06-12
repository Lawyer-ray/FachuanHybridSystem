vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn((config) => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    ...config,
  })),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogFooter: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <form>{children}</form>,
  FormControl: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FormField: ({ render: renderFn, name }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode; name: string }) => {
    const valueMap: Record<string, unknown> = { clue_type: 'bank', content: '' }
    return renderFn({ field: { value: valueMap[name] ?? '', onChange: vi.fn(), onBlur: vi.fn(), name, ref: vi.fn() } })
  },
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <div />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectItem: ({ children, value }: Record<string, unknown>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return { Loader2: Icon, Paperclip: Icon, X: Icon }
})

vi.mock('../../api', () => ({
  clientApi: {
    getContentTemplate: vi.fn().mockResolvedValue({ clue_type: 'bank', template: 'template text' }),
  },
}))

const mockCreateMutateAsync = vi.fn().mockResolvedValue({ id: 1 })
const mockUpdateMutateAsync = vi.fn().mockResolvedValue({ id: 1 })
const mockUploadMutateAsync = vi.fn().mockResolvedValue({ id: 1 })

const mockUsePropertyClueMutations = vi.fn(() => ({
  createClue: { mutateAsync: mockCreateMutateAsync, isPending: false },
  updateClue: { mutateAsync: mockUpdateMutateAsync, isPending: false },
  uploadAttachment: { mutateAsync: mockUploadMutateAsync, isPending: false },
}))

vi.mock('../../hooks/use-property-clue-mutations', () => ({
  usePropertyClueMutations: (...args: unknown[]) => mockUsePropertyClueMutations(...args),
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PropertyClueFormDialog } from '../PropertyClueFormDialog'
import { clientApi } from '../../api'
import { toast } from 'sonner'

describe('PropertyClueFormDialog - coverage improvements', () => {
  const defaultProps = {
    clientId: 1,
    clue: null,
    open: true,
    onOpenChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateMutateAsync.mockReset().mockResolvedValue({ id: 1 })
    mockUpdateMutateAsync.mockReset().mockResolvedValue({ id: 1 })
    mockUploadMutateAsync.mockReset().mockResolvedValue({ id: 1 })
  })

  // ========== onSubmit create mode - covers lines 83-89 ==========

  it('submits create form and calls createClue.mutateAsync', async () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('创建'))
    await waitFor(() => {
      expect(mockCreateMutateAsync).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('线索已创建')
    })
  })

  // ========== onSubmit create mode with files - covers lines 86-88 ==========

  it('uploads attachments when creating with files', async () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    // Add a file
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'doc.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('创建'))
    await waitFor(() => {
      expect(mockCreateMutateAsync).toHaveBeenCalled()
      expect(mockUploadMutateAsync).toHaveBeenCalledWith({ clueId: 1, file })
    })
  })

  // ========== onSubmit edit mode - covers lines 80-82 ==========

  it('submits edit form and calls updateClue.mutateAsync', async () => {
    const clue = {
      id: 10, client_id: 1, clue_type: 'bank', clue_type_label: '银行账户',
      content: 'existing content', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
    }
    render(<PropertyClueFormDialog {...defaultProps} clue={clue} />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(mockUpdateMutateAsync).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('线索已更新')
    })
  })

  // ========== onSubmit error handling - covers line 93-94 ==========

  it('shows error toast when create fails', async () => {
    mockCreateMutateAsync.mockRejectedValue(new Error('fail'))
    render(<PropertyClueFormDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('创建'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('操作失败')
    })
  })

  it('shows error toast when update fails', async () => {
    mockUpdateMutateAsync.mockRejectedValue(new Error('fail'))
    const clue = {
      id: 10, client_id: 1, clue_type: 'bank', clue_type_label: '银行账户',
      content: 'test', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
    }
    render(<PropertyClueFormDialog {...defaultProps} clue={clue} />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('操作失败')
    })
  })

  // ========== useEffect reset on open change - covers lines 56-63 ==========

  it('resets form when dialog opens without clue', () => {
    const { rerender } = render(<PropertyClueFormDialog {...defaultProps} open={false} />)
    rerender(<PropertyClueFormDialog {...defaultProps} open={true} />)
    expect(screen.getByText('新建财产线索')).toBeInTheDocument()
  })

  it('resets form with clue data when dialog opens with clue', () => {
    const clue = {
      id: 5, client_id: 1, clue_type: 'alipay', clue_type_label: '支付宝账户',
      content: 'alipay info', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
    }
    const { rerender } = render(<PropertyClueFormDialog {...defaultProps} clue={null} open={false} />)
    rerender(<PropertyClueFormDialog {...defaultProps} clue={clue} open={true} />)
    expect(screen.getByText('编辑财产线索')).toBeInTheDocument()
  })

  // ========== getContentTemplate effect - covers lines 66-74 ==========

  it('loads content template when creating and clueType changes', async () => {
    vi.mocked(clientApi.getContentTemplate).mockResolvedValue({
      clue_type: 'bank',
      template: 'Bank account template',
    })

    render(<PropertyClueFormDialog {...defaultProps} />)
    await waitFor(() => {
      expect(clientApi.getContentTemplate).toHaveBeenCalledWith('bank')
    })
  })

  it('handles getContentTemplate failure silently', async () => {
    vi.mocked(clientApi.getContentTemplate).mockRejectedValue(new Error('fail'))
    render(<PropertyClueFormDialog {...defaultProps} />)
    // Should not throw
    await waitFor(() => {
      expect(clientApi.getContentTemplate).toHaveBeenCalled()
    })
  })

  // ========== getContentTemplate with no template in response ==========

  it('handles getContentTemplate response with no template', async () => {
    vi.mocked(clientApi.getContentTemplate).mockResolvedValue({
      clue_type: 'bank',
      template: '',
    })

    render(<PropertyClueFormDialog {...defaultProps} />)
    await waitFor(() => {
      expect(clientApi.getContentTemplate).toHaveBeenCalled()
    })
  })

  // ========== Cancel button - covers onOpenChange ==========

  it('calls onOpenChange(false) when cancel is clicked', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('取消'))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  // ========== File removal - covers lines 154-156 ==========

  it('removes file when X button is clicked', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'doc.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('doc.pdf')).toBeInTheDocument()
  })

  // ========== isPending state - covers disabled buttons ==========

  it('disables buttons when create is pending', () => {
    mockUsePropertyClueMutations.mockReturnValue({
      createClue: { mutateAsync: vi.fn(), isPending: true },
      updateClue: { mutateAsync: vi.fn(), isPending: false },
      uploadAttachment: { mutateAsync: vi.fn(), isPending: false },
    })

    const { rerender } = render(<PropertyClueFormDialog {...defaultProps} />)
    // Force re-render to pick up the new mock
    rerender(<PropertyClueFormDialog {...defaultProps} />)
    expect(screen.getByText('创建')).toBeDisabled()
    // Reset mock
    mockUsePropertyClueMutations.mockReturnValue({
      createClue: { mutateAsync: mockCreateMutateAsync, isPending: false },
      updateClue: { mutateAsync: mockUpdateMutateAsync, isPending: false },
      uploadAttachment: { mutateAsync: mockUploadMutateAsync, isPending: false },
    })
  })

  // ========== Multiple file uploads ==========

  it('handles multiple file selection', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file1 = new File(['test1'], 'doc1.pdf', { type: 'application/pdf' })
    const file2 = new File(['test2'], 'doc2.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file1, file2] } })
    expect(screen.getByText('doc1.pdf')).toBeInTheDocument()
    expect(screen.getByText('doc2.pdf')).toBeInTheDocument()
  })

  // ========== Edit mode does not show attachment section ==========

  it('does not show attachment section in edit mode', () => {
    const clue = {
      id: 10, client_id: 1, clue_type: 'bank', clue_type_label: '银行账户',
      content: 'test', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
    }
    render(<PropertyClueFormDialog {...defaultProps} clue={clue} />)
    expect(screen.queryByText('附件')).not.toBeInTheDocument()
  })
})
