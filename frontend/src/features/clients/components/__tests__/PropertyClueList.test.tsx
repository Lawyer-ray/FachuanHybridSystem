vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/date', () => ({
  formatDateOnly: vi.fn((d: string) => d || '-'),
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: vi.fn((url: string | null) => url),
  API_BASE_URL: 'http://localhost:8002/api/v1',
  BACKEND_URL: 'http://localhost:8002',
  createFeatureApiClient: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
  CardContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...p }: Record<string, unknown>) => <span {...p}>{children}</span>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: Record<string, unknown>) => <button>{children}</button>,
  AlertDialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: Record<string, unknown>) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    Plus: Icon, Trash2: Icon, Edit: Icon, Paperclip: Icon,
    Upload: Icon, FileText: Icon, ChevronDown: Icon, ChevronUp: Icon,
  }
})

vi.mock('../../hooks/use-property-clues', () => ({
  usePropertyClues: vi.fn(() => ({ data: [], isLoading: false })),
}))

vi.mock('../../hooks/use-property-clue-mutations', () => ({
  usePropertyClueMutations: vi.fn(() => ({
    deleteClue: { mutateAsync: vi.fn(), isPending: false },
    uploadAttachment: { mutateAsync: vi.fn(), isPending: false },
    deleteAttachment: { mutateAsync: vi.fn(), isPending: false },
    createClue: { mutateAsync: vi.fn(), isPending: false },
    updateClue: { mutateAsync: vi.fn(), isPending: false },
  })),
}))

vi.mock('../../components/PropertyClueFormDialog', () => ({
  PropertyClueFormDialog: () => <div data-testid="clue-form-dialog">PropertyClueFormDialog</div>,
}))

import { render, screen } from '@testing-library/react'
import { PropertyClueList } from '../PropertyClueList'
import { usePropertyClues } from '../../hooks/use-property-clues'
import type { PropertyClue } from '../../types'

const mockClue: PropertyClue = {
  id: 1,
  client_id: 1,
  clue_type: 'bank',
  clue_type_label: '银行账户',
  content: 'test bank account info',
  attachments: [],
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

describe('PropertyClueList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton when loading', () => {
    vi.mocked(usePropertyClues).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('renders empty state when no clues', () => {
    vi.mocked(usePropertyClues).mockReturnValue({
      data: [],
      isLoading: false,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(screen.getByText('暂无财产线索')).toBeInTheDocument()
  })

  it('renders create button', () => {
    vi.mocked(usePropertyClues).mockReturnValue({
      data: [],
      isLoading: false,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(screen.getByText('新建线索')).toBeInTheDocument()
  })

  it('renders clue cards when clues are provided', () => {
    vi.mocked(usePropertyClues).mockReturnValue({
      data: [mockClue],
      isLoading: false,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(screen.getByText('银行账户')).toBeInTheDocument()
    expect(screen.getByText('test bank account info')).toBeInTheDocument()
  })

  it('shows clue count', () => {
    vi.mocked(usePropertyClues).mockReturnValue({
      data: [mockClue, { ...mockClue, id: 2 }],
      isLoading: false,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(screen.getByText('共 2 条财产线索')).toBeInTheDocument()
  })

  it('renders attachment info when clues have attachments', () => {
    const clueWithAttachments = {
      ...mockClue,
      attachments: [{
        id: 1,
        file_path: '/test.pdf',
        file_name: 'test.pdf',
        uploaded_at: '2024-01-01',
        media_url: '/media/test.pdf',
      }],
    }

    vi.mocked(usePropertyClues).mockReturnValue({
      data: [clueWithAttachments],
      isLoading: false,
    } as ReturnType<typeof usePropertyClues>)

    render(<PropertyClueList clientId={1} />)
    expect(screen.getByText('1 个附件')).toBeInTheDocument()
  })
})
