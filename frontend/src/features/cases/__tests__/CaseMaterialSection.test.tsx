import { render, screen } from '@testing-library/react'
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

vi.mock('@/lib/date', () => ({
  formatDateOnly: (d: string) => d ?? '',
}))

vi.mock('../hooks/use-material-mutations', () => ({
  useMaterialMutations: () => ({
    createMaterial: { mutate: vi.fn(), isPending: false },
    updateMaterial: { mutate: vi.fn(), isPending: false },
    deleteMaterial: { mutate: vi.fn(), isPending: false },
    reorderMaterials: { mutate: vi.fn() },
    bindMaterials: { mutate: vi.fn(), isPending: false },
    unbindMaterials: { mutate: vi.fn(), isPending: false },
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
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('CaseMaterialSection', () => {
  it('renders empty state when no candidates', () => {
    render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(screen.getByText('暂无材料数据')).toBeInTheDocument()
  })

  it('renders without crashing with editable prop', () => {
    const { container } = render(<CaseMaterialSection candidates={[]} caseId={1} editable />)
    expect(container).toBeTruthy()
  })

  it('renders without crashing when not editable', () => {
    const { container } = render(<CaseMaterialSection candidates={[]} caseId={1} />)
    expect(container).toBeTruthy()
  })


})
