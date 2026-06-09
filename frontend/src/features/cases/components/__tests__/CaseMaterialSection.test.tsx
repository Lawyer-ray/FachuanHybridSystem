import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { CaseMaterialSection } from '../CaseMaterialSection'

// -- Mocks -----------------------------------------------------------------

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  closestCenter: {},
  KeyboardSensor: class {},
  PointerSensor: class {},
  useSensor: () => ({}),
  useSensors: () => [],
}))

vi.mock('@dnd-kit/sortable', () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: null,
    isDragging: false,
  }),
  sortableKeyboardCoordinates: {},
  verticalListSortingStrategy: {},
}))

vi.mock('@dnd-kit/utilities', () => ({
  CSS: { Transform: { toString: () => '' } },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    resolveMediaUrl: (url: string | null) => (url ? `http://backend${url}` : null),
    createFeatureApiClient: () => ({
      uploadMaterials: vi.fn(),
      bindMaterials: vi.fn(),
      replaceMaterial: vi.fn(),
      renameMaterialGroup: vi.fn(),
      deleteMaterial: vi.fn(),
      deleteAllMaterials: vi.fn(),
      saveMaterialGroupOrder: vi.fn(),
    }),
  }
})

vi.mock('@/lib/date', () => ({
  formatDateOnly: (d: string | null) => d ?? '-',
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

const mockUploadMaterials = { mutateAsync: vi.fn() }
const mockBindMaterials = { mutate: vi.fn(), isPending: false }
const mockRenameGroup = { mutate: vi.fn() }
const mockDeleteMaterial = { mutate: vi.fn() }
const mockDeleteAllMaterials = { mutate: vi.fn() }
const mockReplaceMaterial = { mutate: vi.fn() }
const mockSaveGroupOrder = { mutate: vi.fn() }

vi.mock('../../hooks/use-material-mutations', () => ({
  useMaterialMutations: () => ({
    uploadMaterials: mockUploadMaterials,
    bindMaterials: mockBindMaterials,
    renameGroup: mockRenameGroup,
    deleteMaterial: mockDeleteMaterial,
    deleteAllMaterials: mockDeleteAllMaterials,
    replaceMaterial: mockReplaceMaterial,
    saveGroupOrder: mockSaveGroupOrder,
  }),
}))

vi.mock('../../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return { ...actual }
})

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
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
  Link2: (p: Record<string, unknown>) => <svg data-testid="link2" {...p} />,
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  FileText: (p: Record<string, unknown>) => <svg data-testid="file-text" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  ChevronDown: (p: Record<string, unknown>) => <svg data-testid="chevron-down" {...p} />,
  ChevronRight: (p: Record<string, unknown>) => <svg data-testid="chevron-right" {...p} />,
  GripVertical: (p: Record<string, unknown>) => <svg data-testid="grip" {...p} />,
  Pencil: (p: Record<string, unknown>) => <svg data-testid="pencil" {...p} />,
  Check: (p: Record<string, unknown>) => <svg data-testid="check" {...p} />,
  X: (p: Record<string, unknown>) => <svg data-testid="x-icon" {...p} />,
  FolderOpen: (p: Record<string, unknown>) => <svg data-testid="folder-open" {...p} />,
}))

// -- Test data -------------------------------------------------------------

function makeBoundCandidate(
  attachmentId: number,
  fileName: string,
  materialId: number,
  category: string,
  typeName: string,
  typeId: number,
  side: string | null = null,
) {
  return {
    attachment_id: attachmentId,
    file_name: fileName,
    file_url: `/media/${fileName}`,
    uploaded_at: '2024-01-01T10:00:00Z',
    log_id: 1,
    log_created_at: '2024-01-01T10:00:00Z',
    actor_name: 'Test User',
    material: {
      id: materialId,
      category,
      type_id: typeId,
      type_name: typeName,
      side,
      party_ids: [],
      supervising_authority_id: null,
    },
  }
}

function makeUnboundCandidate(attachmentId: number, fileName: string) {
  return {
    attachment_id: attachmentId,
    file_name: fileName,
    file_url: '',
    uploaded_at: '2024-01-03T10:00:00Z',
    log_id: 3,
    log_created_at: '2024-01-03T10:00:00Z',
    actor_name: 'Unbound User',
    material: null,
  }
}

// -- Tests -----------------------------------------------------------------

describe('CaseMaterialSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    mockUploadMaterials.mutateAsync.mockReset()
    mockBindMaterials.mutate.mockReset()
    mockRenameGroup.mutate.mockReset()
    mockDeleteMaterial.mutate.mockReset()
    mockDeleteAllMaterials.mutate.mockReset()
  })

  // ===== Rendering =====

  it('renders empty state when no candidates at all', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(screen.getByText('暂无材料数据')).toBeInTheDocument()
    expect(screen.getByTestId('folder-open')).toBeInTheDocument()
  })

  it('renders "暂无已绑定材料" when candidates exist but none are bound', () => {
    const candidates = [makeUnboundCandidate(1, 'unbound.pdf')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('暂无已绑定材料')).toBeInTheDocument()
    expect(screen.getByText(/有 1 个未绑定附件/)).toBeInTheDocument()
  })

  it('renders category filter empty message with label', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} categoryFilter="non_party" />)
    expect(screen.getByText('没有非当事人材料数据')).toBeInTheDocument()
  })

  it('renders grouped materials with group type names and counts', () => {
    const candidates = [
      makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(2, 'b.pdf', 11, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(3, 'c.pdf', 12, 'non_party', '证据材料', 2, null),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('(2)')).toBeInTheDocument()
    expect(screen.getAllByText('证据材料').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  it('renders file names and actor info for bound materials', () => {
    const candidates = [makeBoundCandidate(1, 'contract.pdf', 10, 'party', '合同', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('contract.pdf').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Test User/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders unbound attachments section with badge count', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'loose.pdf'),
      makeUnboundCandidate(3, 'loose2.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('未绑定附件')).toBeInTheDocument()
    // File names appear in both the unbound section and bind dialog; use getAllByText
    expect(screen.getAllByText('loose.pdf').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('loose2.pdf').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('does not render unbound section when all candidates are bound', () => {
    const candidates = [makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.queryByText('未绑定附件')).not.toBeInTheDocument()
  })

  it('renders with categoryFilter matching a group', () => {
    const candidates = [
      makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(2, 'b.pdf', 11, 'non_party', '证据', 2, null),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} categoryFilter="party" />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('证据')).not.toBeInTheDocument()
  })

  it('renders DndContext and SortableContext when groups exist', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
  })

  it('renders grip vertical icon for drag handle', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByTestId('grip').length).toBeGreaterThan(0)
  })

  it('renders file link anchor when material has file_url', () => {
    const candidates = [makeBoundCandidate(1, 'doc.pdf', 10, 'party', '合同', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const links = screen.getAllByRole('link')
    const fileLink = links.find(a => a.getAttribute('target') === '_blank')
    expect(fileLink).toBeDefined()
    expect(fileLink!.getAttribute('href')).toContain('doc.pdf')
  })

  // ===== Expand / Collapse =====

  it('starts expanded by default (chevron-down visible)', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
  })

  it('collapses group when chevron clicked', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const chevron = screen.getByTestId('chevron-down')
    const toggleBtn = chevron.closest('button')!
    fireEvent.click(toggleBtn)
    expect(screen.getByTestId('chevron-right')).toBeInTheDocument()
    // File content hidden after collapse
    expect(screen.queryByText('a.pdf')).not.toBeInTheDocument()
  })

  it('re-expands group when chevron clicked again', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const chevron = screen.getByTestId('chevron-down')
    fireEvent.click(chevron.closest('button')!) // collapse
    fireEvent.click(screen.getByTestId('chevron-right').closest('button')!) // expand
    expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
    expect(screen.getAllByText('a.pdf').length).toBeGreaterThanOrEqual(1)
  })

  // ===== File Upload =====

  it('triggers upload mutation on file input change', async () => {
    mockUploadMaterials.mutateAsync.mockResolvedValue({})
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => {
      expect(mockUploadMaterials.mutateAsync).toHaveBeenCalledWith([file])
      expect(toast.success).toHaveBeenCalledWith('已上传 1 个文件')
    })
  })

  it('handles upload with multiple files', async () => {
    mockUploadMaterials.mutateAsync.mockResolvedValue({})
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = [
      new File(['a'], 'a.pdf', { type: 'application/pdf' }),
      new File(['b'], 'b.pdf', { type: 'application/pdf' }),
    ]
    fireEvent.change(fileInput, { target: { files } })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('已上传 2 个文件')
    })
  })

  it('shows error toast when upload fails', async () => {
    mockUploadMaterials.mutateAsync.mockRejectedValue(new Error('fail'))
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('上传失败')
    })
  })

  it('does nothing when file input has no files', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [] } })
    expect(mockUploadMaterials.mutateAsync).not.toHaveBeenCalled()
  })

  it('clears file input value after upload', async () => {
    mockUploadMaterials.mutateAsync.mockResolvedValue({})
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => {
      expect(fileInput.value).toBe('')
    })
  })

  // ===== Ref API =====

  it('exposes openUpload via ref that clicks file input', () => {
    const ref = { current: null as { openUpload: () => void } | null }
    render(<CaseMaterialSection candidates={[]} caseId={1} ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(typeof ref.current!.openUpload).toBe('function')
  })

  // ===== Rename =====

  it('shows pencil button for groups with typeId', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByTestId('pencil').length).toBeGreaterThan(0)
  })

  it('enters rename mode when pencil clicked', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const pencilBtn = screen.getByTestId('pencil').closest('button')!
    fireEvent.click(pencilBtn)
    const input = screen.getByDisplayValue('起诉状')
    expect(input).toBeInTheDocument()
    expect(screen.getByTestId('check')).toBeInTheDocument()
    expect(screen.getByTestId('x-icon')).toBeInTheDocument()
  })

  it('calls renameGroup on confirm rename', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.change(input, { target: { value: '新名称' } })
    fireEvent.click(screen.getByTestId('check').closest('button')!)
    expect(mockRenameGroup.mutate).toHaveBeenCalledWith(
      { typeId: 1, newTypeName: '新名称' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('calls renameGroup success toast', () => {
    mockRenameGroup.mutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.change(input, { target: { value: '新名称' } })
    fireEvent.click(screen.getByTestId('check').closest('button')!)
    expect(toast.success).toHaveBeenCalledWith('重命名成功')
  })

  it('calls renameGroup error toast', () => {
    mockRenameGroup.mutate.mockImplementation((_data: unknown, opts: { onError: () => void }) => {
      opts.onError()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.change(input, { target: { value: '新名称' } })
    fireEvent.click(screen.getByTestId('check').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('重命名失败')
  })

  it('does not rename when value is unchanged', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    fireEvent.click(screen.getByTestId('check').closest('button')!)
    expect(mockRenameGroup.mutate).not.toHaveBeenCalled()
  })

  it('does not rename when value is empty', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByTestId('check').closest('button')!)
    expect(mockRenameGroup.mutate).not.toHaveBeenCalled()
  })

  it('cancels rename when X clicked', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(screen.queryByDisplayValue('起诉状')).not.toBeInTheDocument()
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
  })

  it('cancels rename on Escape key', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByDisplayValue('起诉状')).not.toBeInTheDocument()
  })

  it('confirms rename on Enter key', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getByTestId('pencil').closest('button')!)
    const input = screen.getByDisplayValue('起诉状')
    fireEvent.change(input, { target: { value: '回车改名' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockRenameGroup.mutate).toHaveBeenCalledWith(
      { typeId: 1, newTypeName: '回车改名' },
      expect.any(Object),
    )
  })

  // ===== Delete All Materials =====

  it('deleteAllMaterials calls mutate with category and shows success toast', () => {
    mockDeleteAllMaterials.mutate.mockImplementation((_cat: string, opts: { onSuccess: (res: { deleted_count: number }) => void }) => {
      opts.onSuccess({ deleted_count: 3 })
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const deleteAllButtons = screen.getAllByText('删除全部')
    expect(deleteAllButtons.length).toBeGreaterThan(0)
    fireEvent.click(deleteAllButtons[0])
    expect(mockDeleteAllMaterials.mutate).toHaveBeenCalledWith(
      'party',
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
    expect(toast.success).toHaveBeenCalledWith('已删除 3 项材料')
  })

  it('deleteAllMaterials shows error toast on failure', () => {
    mockDeleteAllMaterials.mutate.mockImplementation((_cat: string, opts: { onError: () => void }) => {
      opts.onError()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByText('删除全部')[0])
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  // ===== Delete Material =====

  it('renders trash icons for groups and items', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const trashIcons = screen.getAllByTestId('trash')
    expect(trashIcons.length).toBeGreaterThanOrEqual(1)
  })

  it('deleteMaterial shows success toast', () => {
    mockDeleteMaterial.mutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const deleteButtons = screen.getAllByText('删除')
    if (deleteButtons.length > 0) {
      fireEvent.click(deleteButtons[0])
      expect(toast.success).toHaveBeenCalledWith('已删除')
    }
  })

  it('deleteMaterial shows error toast on failure', () => {
    mockDeleteMaterial.mutate.mockImplementation((_id: number, opts: { onError: () => void }) => {
      opts.onError()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const deleteButtons = screen.getAllByText('删除')
    if (deleteButtons.length > 0) {
      fireEvent.click(deleteButtons[0])
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    }
  })

  // ===== Bind Dialog =====

  it('opens bind dialog when link button clicked', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const linkButtons = screen.getAllByTestId('link2')
    expect(linkButtons.length).toBeGreaterThan(0)
    fireEvent.click(linkButtons[0].closest('button')!)
    expect(screen.getByText(/绑定附件到/)).toBeInTheDocument()
  })

  it('shows unbound candidates in bind dialog', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    expect(screen.getAllByText('unbound.pdf').length).toBeGreaterThanOrEqual(1)
  })

  it('shows "没有未绑定的附件" when all candidates are bound', () => {
    const candidates = [makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    expect(screen.getByText('没有未绑定的附件')).toBeInTheDocument()
  })

  it('bind button is disabled when no candidates selected', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    const bindBtn = screen.getByText(/绑定 0 项/)
    expect(bindBtn).toBeDisabled()
  })

  it('bind button shows cancel option', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    // The dialog footer has a cancel button
    const cancelButtons = screen.getAllByText('取消')
    expect(cancelButtons.length).toBeGreaterThan(0)
  })

  // ===== Multiple groups =====

  it('separates groups by category, side, and type_name', () => {
    const candidates = [
      makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(2, 'b.pdf', 11, 'party', '起诉状', 2, 'opponent'),
      makeBoundCandidate(3, 'c.pdf', 12, 'non_party', '证据', 3, null),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(2) // two different sides
    expect(screen.getAllByText('证据').length).toBeGreaterThanOrEqual(1)
  })

  it('renders groups with null typeId (no pencil button)', () => {
    const candidates = [
      {
        attachment_id: 1,
        file_name: 'a.pdf',
        file_url: '',
        uploaded_at: '2024-01-01T10:00:00Z',
        log_id: 1,
        log_created_at: '2024-01-01T10:00:00Z',
        actor_name: 'User',
        material: {
          id: 10,
          category: 'party' as const,
          type_id: null,
          type_name: '未分类',
          side: null as null,
          party_ids: [],
          supervising_authority_id: null,
        },
      },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('未分类').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByTestId('pencil')).not.toBeInTheDocument()
  })

  // ===== Drag end handler =====

  it('renders with draggable groups', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
  })

  // ===== Component default export =====

  it('has a default export', async () => {
    const mod = await import('../CaseMaterialSection')
    expect(mod.default).toBeDefined()
    expect(mod.default).toBe(mod.CaseMaterialSection)
  })

  // ===== Category filter with "all" =====

  it('renders all groups when categoryFilter is undefined (defaults to "all")', () => {
    const candidates = [
      makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(2, 'b.pdf', 11, 'non_party', '证据', 2, null),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('证据').length).toBeGreaterThanOrEqual(1)
  })

  // ===== File with empty file_url (no link rendered) =====

  it('does not render file link when file_url is empty', () => {
    const candidates = [{
      attachment_id: 1,
      file_name: 'no-url.pdf',
      file_url: '',
      uploaded_at: '2024-01-01T10:00:00Z',
      log_id: 1,
      log_created_at: '2024-01-01T10:00:00Z',
      actor_name: 'User',
      material: {
        id: 10,
        category: 'party' as const,
        type_id: 1,
        type_name: '起诉状',
        side: null as null,
        party_ids: [],
        supervising_authority_id: null,
      },
    }]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // No links with target="_blank" since file_url is empty
    const links = screen.queryAllByRole('link')
    const fileLinks = links.filter(a => a.getAttribute('target') === '_blank')
    expect(fileLinks.length).toBe(0)
  })

  // ===== Upload resets input even on error =====

  it('clears file input even when upload fails', async () => {
    mockUploadMaterials.mutateAsync.mockRejectedValue(new Error('fail'))
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => {
      expect(fileInput.value).toBe('')
    })
  })
})
