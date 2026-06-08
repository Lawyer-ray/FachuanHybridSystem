import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ArchiveTab } from '../components/ArchiveTab'

vi.mock('lucide-react', () => ({
  Upload: () => <svg />,
  Trash2: () => <svg />,
  Archive: () => <svg />,
  FolderSync: () => <svg />,
  GripVertical: () => <svg />,
  FileCheck: () => <svg />,
  Loader2: () => <svg />,
  Scaling: () => <svg />,
  ArrowRightLeft: () => <svg />,
  ChevronDown: () => <svg />,
  ChevronRight: () => <svg />,
  Download: () => <svg />,
  Eye: () => <svg />,
  FolderOpen: () => <svg />,
  Sparkles: () => <svg />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  closestCorners: {},
  KeyboardSensor: class {},
  PointerSensor: class {},
  useSensor: () => ({}),
  useSensors: () => [],
}))

vi.mock('@dnd-kit/sortable', () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  useSortable: () => ({ attributes: {}, listeners: {}, setNodeRef: vi.fn(), transform: null, transition: null }),
  verticalListSortingStrategy: {},
  arrayMove: vi.fn(),
  sortableKeyboardCoordinates: {},
}))

vi.mock('@dnd-kit/utilities', () => ({
  CSS: { Transform: { toString: () => '' } },
}))

vi.mock('../api', () => ({
  contractApi: {
    fetchChecklist: vi.fn().mockResolvedValue(null),
    saveChecklist: vi.fn(),
    finalizeArchive: vi.fn(),
    updateChecklistItem: vi.fn(),
    addChecklistMaterial: vi.fn(),
    deleteChecklistMaterial: vi.fn(),
    reorderChecklistMaterials: vi.fn(),
  },
}))

vi.mock('../components/FolderScanPanel', () => ({
  FolderScanPanel: () => <div data-testid="folder-scan-panel" />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
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
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

const mockContract = {
  id: 1,
  cases: [{ id: 10, name: '测试案件' }],
}

function renderWithProviders(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ArchiveTab', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<ArchiveTab contract={mockContract as never} />)
    expect(container).toBeTruthy()
  })

  it('renders component tree', () => {
    const { container } = renderWithProviders(<ArchiveTab contract={mockContract as never} />)
    expect(container.firstChild).toBeTruthy()
  })
})
