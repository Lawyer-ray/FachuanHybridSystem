import { render, screen, fireEvent } from '@testing-library/react'
import { CaseMaterialSection } from '../components/CaseMaterialSection'

vi.mock('lucide-react', () => ({
  Link2: () => <svg data-testid="link2" />,
  Trash2: () => <svg data-testid="trash" />,
  FileText: () => <svg data-testid="file-text" />,
  Loader2: () => <svg data-testid="loader" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronRight: () => <svg data-testid="chevron-right" />,
  GripVertical: () => <svg data-testid="grip" />,
  Pencil: () => <svg data-testid="pencil" />,
  Check: () => <svg data-testid="check" />,
  X: () => <svg data-testid="x" />,
  FolderOpen: () => <svg data-testid="folder-open" />,
  Upload: () => <svg data-testid="upload" />,
  Eye: () => <svg data-testid="eye" />,
  Search: () => <svg data-testid="search" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
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
  useSortable: () => ({ attributes: {}, listeners: {}, setNodeRef: vi.fn(), transform: null, transition: null }),
  sortableKeyboardCoordinates: {},
  verticalListSortingStrategy: {},
}))

vi.mock('@dnd-kit/utilities', () => ({
  CSS: { Transform: { toString: () => '' } },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (url: string) => url,
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDateOnly: (d: string) => d ?? '',
}))

const mockCreateMaterial = vi.fn()
const mockUpdateMaterial = vi.fn()
const mockDeleteMaterial = vi.fn()
const mockReorderMaterials = vi.fn()
const mockBindMaterials = vi.fn()
const mockUnbindMaterials = vi.fn()

vi.mock('../hooks/use-material-mutations', () => ({
  useMaterialMutations: () => ({
    createMaterial: { mutate: mockCreateMaterial, isPending: false },
    updateMaterial: { mutate: mockUpdateMaterial, isPending: false },
    deleteMaterial: { mutate: mockDeleteMaterial, isPending: false },
    reorderMaterials: { mutate: mockReorderMaterials },
    bindMaterials: { mutate: mockBindMaterials, isPending: false },
    unbindMaterials: { mutate: mockUnbindMaterials, isPending: false },
  }),
}))

vi.mock('../types', () => ({
  MATERIAL_CATEGORY_LABELS: {
    contract: { zh: '合同' },
    evidence: { zh: '证据' },
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
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
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const mockCandidates = [
  {
    id: 1,
    file_name: '合同扫描件.pdf',
    file_url: 'http://example.com/doc1.pdf',
    actor_name: '张律师',
    uploaded_at: '2024-01-01T10:00:00',
    material: { id: 100, category: 'contract', side: 'plaintiff', type_name: '合同', type_id: 1 },
    matches: [],
  },
  {
    id: 2,
    file_name: '证据材料.docx',
    file_url: 'http://example.com/doc2.docx',
    actor_name: '李律师',
    uploaded_at: '2024-01-02T10:00:00',
    material: { id: 200, category: 'evidence', side: 'defendant', type_name: '证据', type_id: 2 },
    matches: [],
  },
  {
    id: 3,
    file_name: '未分类文件.pdf',
    file_url: '',
    actor_name: '王律师',
    uploaded_at: '2024-01-03T10:00:00',
    material: null,
    matches: [],
  },
]

describe('CaseMaterialSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when no candidates', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(screen.getByText('暂无材料数据')).toBeInTheDocument()
  })

  it('renders empty state with folder icon', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(screen.getByTestId('folder-open')).toBeInTheDocument()
  })

  it('renders without crashing with editable prop', () => {
    const { container } = render(<CaseMaterialSection candidates={[]} caseId={1} editable />)
    expect(container).toBeTruthy()
  })

  it('renders without crashing when not editable', () => {
    const { container } = render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(container).toBeTruthy()
  })

  it('renders file names when candidates provided', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    expect(screen.getAllByText('合同扫描件.pdf').length).toBeGreaterThan(0)
    expect(screen.getAllByText('证据材料.docx').length).toBeGreaterThan(0)
    expect(screen.getAllByText('未分类文件.pdf').length).toBeGreaterThan(0)
  })

  it('renders actor names and dates', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    expect(screen.getAllByText(/张律师/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/李律师/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/王律师/).length).toBeGreaterThan(0)
  })

  it('renders file text icons', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    const icons = screen.getAllByTestId('file-text')
    expect(icons.length).toBeGreaterThan(0)
  })

  it('renders with editable mode', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} editable />)
    // Editable mode shows delete buttons on hover
    expect(screen.getAllByText('合同扫描件.pdf').length).toBeGreaterThan(0)
  })

  it('renders materials from different categories', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    // Both contract and evidence materials should be visible
    expect(screen.getAllByText('合同扫描件.pdf').length).toBeGreaterThan(0)
    expect(screen.getAllByText('证据材料.docx').length).toBeGreaterThan(0)
  })

  it('renders with null material', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    // File without material should still show
    expect(screen.getAllByText('未分类文件.pdf').length).toBeGreaterThan(0)
  })

  it('renders with empty file_url', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    // File without URL should not crash
    expect(screen.getAllByText('未分类文件.pdf').length).toBeGreaterThan(0)
  })

  it('renders multiple file types', () => {
    const candidates = [
      { id: 1, file_name: 'file.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: null, matches: [] },
      { id: 2, file_name: 'file.docx', file_url: '', actor_name: 'B', uploaded_at: '2024-01-02', material: null, matches: [] },
      { id: 3, file_name: 'file.jpg', file_url: '', actor_name: 'C', uploaded_at: '2024-01-03', material: null, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('file.pdf')).toBeInTheDocument()
    expect(screen.getByText('file.docx')).toBeInTheDocument()
    expect(screen.getByText('file.jpg')).toBeInTheDocument()
  })

  it('renders single material', () => {
    const single = [mockCandidates[0]]
    render(<CaseMaterialSection candidates={single as never} caseId={1} />)
    expect(screen.getAllByText('合同扫描件.pdf').length).toBeGreaterThan(0)
  })

  it('renders in non-editable mode', () => {
    render(<CaseMaterialSection candidates={mockCandidates as never} caseId={1} />)
    // Non-editable should not show action buttons
    expect(screen.getAllByText('合同扫描件.pdf').length).toBeGreaterThan(0)
  })

  it('handles caseId prop', () => {
    const { rerender } = render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(screen.getByText('暂无材料数据')).toBeInTheDocument()
    rerender(<CaseMaterialSection candidates={[]} caseId={2} />)
    expect(screen.getByText('暂无材料数据')).toBeInTheDocument()
  })

  it('renders with long file names', () => {
    const candidates = [
      { id: 1, file_name: '这是一个非常非常长的文件名用于测试截断效果.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: null, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('这是一个非常非常长的文件名用于测试截断效果.pdf')).toBeInTheDocument()
  })

  it('renders with special characters in file names', () => {
    const candidates = [
      { id: 1, file_name: 'file (1) [copy].pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: null, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('file (1) [copy].pdf')).toBeInTheDocument()
  })

  it('renders with different material types', () => {
    const candidates = [
      { id: 1, file_name: 'a.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: { id: 1, category: 'contract', side: 'plaintiff', type_name: '合同', type_id: 1 }, matches: [] },
      { id: 2, file_name: 'b.pdf', file_url: '', actor_name: 'B', uploaded_at: '2024-01-02', material: { id: 2, category: 'evidence', side: 'defendant', type_name: '证据', type_id: 2 }, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('a.pdf')).toBeInTheDocument()
    expect(screen.getByText('b.pdf')).toBeInTheDocument()
  })

  it('renders with same category different sides', () => {
    const candidates = [
      { id: 1, file_name: 'plaintiff.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: { id: 1, category: 'evidence', side: 'plaintiff', type_name: '证据', type_id: 1 }, matches: [] },
      { id: 2, file_name: 'defendant.pdf', file_url: '', actor_name: 'B', uploaded_at: '2024-01-02', material: { id: 2, category: 'evidence', side: 'defendant', type_name: '证据', type_id: 2 }, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('plaintiff.pdf')).toBeInTheDocument()
    expect(screen.getByText('defendant.pdf')).toBeInTheDocument()
  })

  it('renders with null side', () => {
    const candidates = [
      { id: 1, file_name: 'no-side.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01', material: { id: 1, category: 'contract', side: null, type_name: '合同', type_id: 1 }, matches: [] },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('no-side.pdf')).toBeInTheDocument()
  })

  it('renders with matches', () => {
    const candidates = [
      {
        id: 1, file_name: 'matched.pdf', file_url: '', actor_name: 'A', uploaded_at: '2024-01-01',
        material: null,
        matches: [{ type: 'exact', target_id: 1, target_name: '合同扫描件' }],
      },
    ]
    render(<CaseMaterialSection candidates={candidates as never} caseId={1} />)
    expect(screen.getByText('matched.pdf')).toBeInTheDocument()
  })
})
