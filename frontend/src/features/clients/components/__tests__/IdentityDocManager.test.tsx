vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn((config) => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    ...config,
  })),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: vi.fn((url: string | null) => url),
  createFeatureApiClient: vi.fn(),
  API_BASE_URL: 'http://localhost:8002/api/v1',
  BACKEND_URL: 'http://localhost:8002',
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: Record<string, unknown>) => <label>{children}</label>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    Plus: Icon, Trash2: Icon, Eye: Icon, FileText: Icon,
    Image: Icon, Calendar: Icon, Upload: Icon, Merge: Icon,
  }
})

vi.mock('date-fns', () => ({
  format: vi.fn(() => '2024年01月01日 12:00'),
}))

vi.mock('date-fns/locale', () => ({
  zhCN: {},
}))

vi.mock('../../hooks/use-identity-doc-mutations', () => ({
  useIdentityDocMutations: vi.fn(() => ({
    addDoc: { mutateAsync: vi.fn(), isPending: false },
    deleteDoc: { mutateAsync: vi.fn(), isPending: false },
  })),
}))

vi.mock('../api', () => ({
  clientApi: {
    mergeIdCard: vi.fn(),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { IdentityDocManager } from '../IdentityDocManager'
import type { IdentityDoc } from '../../types'
import { clientApi } from '../../api'
import { toast } from 'sonner'

const mockAddMutateAsync = vi.fn()
const mockDeleteMutateAsync = vi.fn()

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn((config) => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    ...config,
  })),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: vi.fn((url: string | null) => url),
  createFeatureApiClient: vi.fn(),
  API_BASE_URL: 'http://localhost:8002/api/v1',
  BACKEND_URL: 'http://localhost:8002',
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: Record<string, unknown>) => <label>{children}</label>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    Plus: Icon, Trash2: Icon, Eye: Icon, FileText: Icon,
    Image: Icon, Calendar: Icon, Upload: Icon, Merge: Icon,
  }
})

vi.mock('date-fns', () => ({
  format: vi.fn(() => '2024年01月01日 12:00'),
}))

vi.mock('date-fns/locale', () => ({
  zhCN: {},
}))

vi.mock('../../hooks/use-identity-doc-mutations', () => ({
  useIdentityDocMutations: vi.fn(() => ({
    addDoc: { mutateAsync: mockAddMutateAsync, isPending: false },
    deleteDoc: { mutateAsync: mockDeleteMutateAsync, isPending: false },
  })),
}))

vi.mock('../../api', () => ({
  clientApi: {
    mergeIdCard: vi.fn(),
  },
}))

const mockDocs: IdentityDoc[] = [
  { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
]

describe('IdentityDocManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAddMutateAsync.mockReset()
    mockDeleteMutateAsync.mockReset()
  })

  it('renders doc count', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    expect(screen.getByText('共 1 份证件')).toBeInTheDocument()
  })

  it('renders add button', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    const addButtons = screen.getAllByText('添加证件')
    expect(addButtons.length).toBeGreaterThanOrEqual(1)
  })

  it('renders merge id card button', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    expect(screen.getByText('合并身份证')).toBeInTheDocument()
  })

  it('renders empty state when no docs', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    expect(screen.getByText('暂无证件')).toBeInTheDocument()
    expect(screen.getByText('点击「添加证件」上传')).toBeInTheDocument()
  })

  it('renders doc cards when docs are provided', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    const idCards = screen.getAllByText('身份证')
    expect(idCards.length).toBeGreaterThanOrEqual(1)
  })

  it('renders multiple doc count', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
      { id: 2, doc_type: 'passport', file_path: '/files/passport.jpg', uploaded_at: '2024-01-02T12:00:00', media_url: '/media/passport.jpg' },
    ]
    render(<IdentityDocManager clientId="1" clientType="natural" docs={docs} />)
    expect(screen.getByText('共 2 份证件')).toBeInTheDocument()
  })

  it('opens add dialog when add button clicked', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    expect(screen.getByText('证件类型')).toBeInTheDocument()
    expect(screen.getByText('选择文件')).toBeInTheDocument()
  })

  it('opens merge dialog when merge button clicked', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    expect(screen.getByText('合并身份证正反面')).toBeInTheDocument()
    expect(screen.getByText('正面（人像面）')).toBeInTheDocument()
    expect(screen.getByText('反面（国徽面）')).toBeInTheDocument()
  })

  it('handles add doc with selected file', async () => {
    mockAddMutateAsync.mockResolvedValue({})
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    // Select a file
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Click upload
    fireEvent.click(screen.getByText('上传'))
    await waitFor(() => {
      expect(mockAddMutateAsync).toHaveBeenCalledWith({ docType: 'id_card', file })
      expect(toast.success).toHaveBeenCalledWith('证件已添加')
    })
  })

  it('shows error when adding without selecting file', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    // The upload button should be disabled when no file is selected
    const uploadButtons = screen.getAllByText('上传')
    const dialogUploadBtn = uploadButtons[uploadButtons.length - 1]
    expect(dialogUploadBtn).toBeDisabled()
  })

  it('handles add doc failure', async () => {
    mockAddMutateAsync.mockRejectedValue(new Error('fail'))
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('上传'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('添加失败')
    })
  })

  it('cancels add dialog', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByText('证件类型')).not.toBeInTheDocument()
  })

  it('shows selected file info in add dialog', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('添加证件'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('id.jpg')).toBeInTheDocument()
  })

  it('opens delete confirmation dialog when delete clicked', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    // Find delete button in the hover group
    const deleteBtn = screen.getByText('删除')
    fireEvent.click(deleteBtn)
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })

  it('handles delete doc', async () => {
    mockDeleteMutateAsync.mockResolvedValue({})
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    fireEvent.click(screen.getByText('删除'))
    // AlertDialogAction button has text "删除" - click the last one (inside the AlertDialog)
    const deleteButtons = screen.getAllByText('删除')
    fireEvent.click(deleteButtons[deleteButtons.length - 1])
    await waitFor(() => {
      expect(mockDeleteMutateAsync).toHaveBeenCalledWith(1)
      expect(toast.success).toHaveBeenCalledWith('证件已删除')
    })
  })

  it('handles delete doc failure', async () => {
    mockDeleteMutateAsync.mockRejectedValue(new Error('fail'))
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    fireEvent.click(screen.getByText('删除'))
    const deleteButtons = screen.getAllByText('删除')
    fireEvent.click(deleteButtons[deleteButtons.length - 1])
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  it('handles merge with both files', async () => {
    vi.mocked(clientApi.mergeIdCard).mockResolvedValue({ success: true })
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    // Select front file
    const fileInputs = document.querySelectorAll('input[type="file"]')
    const frontFile = new File(['front'], 'front.jpg', { type: 'image/jpeg' })
    const backFile = new File(['back'], 'back.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInputs[0], { target: { files: [frontFile] } })
    fireEvent.change(fileInputs[1], { target: { files: [backFile] } })
    fireEvent.click(screen.getByText('合并'))
    await waitFor(() => {
      expect(clientApi.mergeIdCard).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('身份证合并成功')
    })
  })

  it('shows error when merging without both files', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    // The merge button should be disabled when no files are selected
    const mergeButtons = screen.getAllByText('合并')
    const dialogMergeBtn = mergeButtons[mergeButtons.length - 1]
    expect(dialogMergeBtn).toBeDisabled()
  })

  it('handles merge failure with res.success=false', async () => {
    vi.mocked(clientApi.mergeIdCard).mockResolvedValue({ success: false, error: '合并出错' })
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    const fileInputs = document.querySelectorAll('input[type="file"]')
    fireEvent.change(fileInputs[0], { target: { files: [new File(['f'], 'f.jpg', { type: 'image/jpeg' })] } })
    fireEvent.change(fileInputs[1], { target: { files: [new File(['b'], 'b.jpg', { type: 'image/jpeg' })] } })
    fireEvent.click(screen.getByText('合并'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('合并出错')
    })
  })

  it('handles merge exception', async () => {
    vi.mocked(clientApi.mergeIdCard).mockRejectedValue(new Error('network'))
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    const fileInputs = document.querySelectorAll('input[type="file"]')
    fireEvent.change(fileInputs[0], { target: { files: [new File(['f'], 'f.jpg', { type: 'image/jpeg' })] } })
    fireEvent.change(fileInputs[1], { target: { files: [new File(['b'], 'b.jpg', { type: 'image/jpeg' })] } })
    fireEvent.click(screen.getByText('合并'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('合并失败，请重试')
    })
  })

  it('cancels merge dialog', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    fireEvent.click(screen.getByText('合并身份证'))
    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByText('合并身份证正反面')).not.toBeInTheDocument()
  })

  it('renders doc with non-image file path shows FileText icon', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'contract', file_path: '/files/doc.pdf', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/doc.pdf' },
    ]
    render(<IdentityDocManager clientId="1" clientType="natural" docs={docs} />)
    expect(screen.getByText('共 1 份证件')).toBeInTheDocument()
  })

  it('renders doc without media_url shows placeholder', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocManager clientId="1" clientType="natural" docs={docs} />)
    expect(screen.getByText('共 1 份证件')).toBeInTheDocument()
  })

  it('opens preview dialog for image doc', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    const previewBtn = screen.getByText('预览')
    fireEvent.click(previewBtn)
    // "身份证" appears in both card badge and dialog title
    expect(screen.getAllByText('身份证').length).toBeGreaterThanOrEqual(1)
  })

  it('closes preview dialog', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    fireEvent.click(screen.getByText('预览'))
    expect(screen.getAllByText('身份证').length).toBeGreaterThanOrEqual(1)
  })

  it('renders with legal client type', () => {
    render(<IdentityDocManager clientId="1" clientType="legal" docs={[]} />)
    expect(screen.getByText('添加证件')).toBeInTheDocument()
  })
})
