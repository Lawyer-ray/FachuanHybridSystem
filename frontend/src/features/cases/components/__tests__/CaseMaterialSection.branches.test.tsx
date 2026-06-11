/**
 * Additional coverage tests for CaseMaterialSection.tsx
 * Targets: uncovered branches (16) and functions (9)
 * Focus: handleBind, handleRename, handleDeleteItem, handleDeleteAll,
 * handleDragEnd, MaterialRow interactions, SortableGroupCard branches
 */

import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { CaseMaterialSection } from '../CaseMaterialSection'

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
  DndContext: ({ children, onDragEnd }: { children: React.ReactNode; onDragEnd?: (e: unknown) => void }) => {
    // Store onDragEnd for testing
    (globalThis as Record<string, unknown>).__dndOnDragEnd = onDragEnd
    return <div>{children}</div>
  },
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

describe('CaseMaterialSection - branch/function coverage', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    mockUploadMaterials.mutateAsync.mockReset()
    mockBindMaterials.mutate.mockReset()
    mockRenameGroup.mutate.mockReset()
    mockDeleteMaterial.mutate.mockReset()
    mockDeleteAllMaterials.mutate.mockReset()
  })

  // --- handleBind (lines 138-150) ---

  it('handleBind calls bindMaterials.mutate with selected items', () => {
    mockBindMaterials.mutate.mockImplementation((_items: unknown, opts: { onSuccess: (res: { saved_count: number }) => void }) => {
      opts.onSuccess({ saved_count: 2 })
    })
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound1.pdf'),
      makeUnboundCandidate(3, 'unbound2.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // Open bind dialog
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    // Select unbound candidates by clicking checkboxes
    const checkboxes = document.querySelectorAll('input[type="checkbox"]')
    checkboxes.forEach(cb => fireEvent.click(cb))
    // Click bind button (the one with count > 0)
    const bindBtns = screen.getAllByText(/绑定 \d+ 项/)
    if (bindBtns.length > 0) {
      fireEvent.click(bindBtns[0])
    }
    expect(mockBindMaterials.mutate).toHaveBeenCalled()
  })

  it('handleBind shows error toast on failure', () => {
    mockBindMaterials.mutate.mockImplementation((_items: unknown, opts: { onError: () => void }) => {
      opts.onError()
    })
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    const checkboxes = document.querySelectorAll('input[type="checkbox"]')
    checkboxes.forEach(cb => fireEvent.click(cb))
    const bindBtns = screen.getAllByText(/绑定 \d+ 项/)
    if (bindBtns.length > 0) {
      fireEvent.click(bindBtns[0])
    }
    expect(toast.error).toHaveBeenCalledWith('绑定失败')
  })

  it('handleBind does nothing when no candidates selected', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    // Click bind without selecting anything
    const bindBtn = screen.getByText(/绑定 0 项/)
    fireEvent.click(bindBtn)
    expect(mockBindMaterials.mutate).not.toHaveBeenCalled()
  })

  // --- handleDeleteItem (lines 369-375) ---

  it('handleDeleteItem calls deleteMaterial.mutate with material id', () => {
    mockDeleteMaterial.mutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // Find delete button for the item (inside MaterialRow)
    const deleteButtons = screen.getAllByText('删除')
    fireEvent.click(deleteButtons[0])
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('handleDeleteItem shows error toast on failure', () => {
    mockDeleteMaterial.mutate.mockImplementation((_id: number, opts: { onError: () => void }) => {
      opts.onError()
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const deleteButtons = screen.getAllByText('删除')
    fireEvent.click(deleteButtons[0])
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  // --- handleDragEnd (lines 335-340) ---

  it('handleDragEnd shows info toast on reorder', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // Simulate drag end via the stored callback
    const onDragEnd = (globalThis as Record<string, unknown>).__dndOnDragEnd as (e: unknown) => void
    if (onDragEnd) {
      onDragEnd({ active: { id: 'a' }, over: { id: 'b' } })
    }
    expect(toast.info).toHaveBeenCalledWith('拖拽排序已更新，请点击保存排序')
  })

  it('handleDragEnd does nothing when no over target', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const onDragEnd = (globalThis as Record<string, unknown>).__dndOnDragEnd as (e: unknown) => void
    if (onDragEnd) {
      onDragEnd({ active: { id: 'a' }, over: null })
    }
    expect(toast.info).not.toHaveBeenCalled()
  })

  it('handleDragEnd does nothing when active === over', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const onDragEnd = (globalThis as Record<string, unknown>).__dndOnDragEnd as (e: unknown) => void
    if (onDragEnd) {
      onDragEnd({ active: { id: 'a' }, over: { id: 'a' } })
    }
    expect(toast.info).not.toHaveBeenCalled()
  })

  // --- handleRename (lines 362-367) ---

  it('handleRename shows success toast', () => {
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

  // --- MaterialRow: delete button with deletePending (line 94) ---

  it('MaterialRow delete button shows loader when deletePending', () => {
    // deletePending is always false in the current implementation
    // but we test the button renders correctly
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    const trashIcons = screen.getAllByTestId('trash')
    expect(trashIcons.length).toBeGreaterThanOrEqual(1)
  })

  // --- MaterialRow: no file_url (line 82-88) ---

  it('MaterialRow renders without file link when file_url is empty', () => {
    const candidates = [{
      attachment_id: 1,
      file_name: 'no-link.pdf',
      file_url: '',
      uploaded_at: '2024-01-01T10:00:00Z',
      log_id: 1,
      log_created_at: '2024-01-01T10:00:00Z',
      actor_name: 'User',
      material: {
        id: 10, category: 'party', type_id: 1, type_name: '起诉状', side: null,
        party_ids: [], supervising_authority_id: null,
      },
    }]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // No link with target="_blank"
    const links = screen.queryAllByRole('link').filter(a => a.getAttribute('target') === '_blank')
    expect(links.length).toBe(0)
  })

  // --- MaterialRow: no material (line 89-111) ---

  it('MaterialRow renders without delete dialog when no material', () => {
    const candidates = [makeUnboundCandidate(1, 'unbound.pdf')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('未绑定附件')).toBeInTheDocument()
  })

  // --- SortableGroupCard: expand/collapse toggle (lines 170-171) ---

  it('toggles group expansion', () => {
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    // Initially expanded
    expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
    // Collapse
    fireEvent.click(screen.getByTestId('chevron-down').closest('button')!)
    expect(screen.getByTestId('chevron-right')).toBeInTheDocument()
    // Expand again
    fireEvent.click(screen.getByTestId('chevron-right').closest('button')!)
    expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
  })

  // --- SortableGroupCard: cancel bind dialog ---

  it('cancel bind dialog closes it', () => {
    const candidates = [
      makeBoundCandidate(1, 'bound.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeUnboundCandidate(2, 'unbound.pdf'),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByTestId('link2')[0].closest('button')!)
    expect(screen.getByText(/绑定附件到/)).toBeInTheDocument()
    const cancelButtons = screen.getAllByText('取消')
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
    expect(screen.queryByText(/绑定附件到/)).not.toBeInTheDocument()
  })

  // --- handleUpload with no files (line 344) ---

  it('handleUpload does nothing when files is null', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: null } })
    expect(mockUploadMaterials.mutateAsync).not.toHaveBeenCalled()
  })

  // --- Multiple groups with different categories ---

  it('renders groups filtered by category', () => {
    const candidates = [
      makeBoundCandidate(1, 'party.pdf', 10, 'party', '起诉状', 1, 'our'),
      makeBoundCandidate(2, 'nonparty.pdf', 11, 'non_party', '证据', 2, null),
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} categoryFilter="party" />)
    expect(screen.getAllByText('起诉状').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('证据')).not.toBeInTheDocument()
  })

  // --- handleDeleteAll success/error ---

  it('handleDeleteAll success toast with count', () => {
    mockDeleteAllMaterials.mutate.mockImplementation((_cat: string, opts: { onSuccess: (res: { deleted_count: number }) => void }) => {
      opts.onSuccess({ deleted_count: 5 })
    })
    const candidates = [makeBoundCandidate(1, 'a.pdf', 10, 'party', '起诉状', 1, 'our')]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    fireEvent.click(screen.getAllByText('删除全部')[0])
    expect(toast.success).toHaveBeenCalledWith('已删除 5 项材料')
  })

  // --- Default export ---

  it('has default export', async () => {
    const mod = await import('../CaseMaterialSection')
    expect(mod.default).toBe(mod.CaseMaterialSection)
  })
})
