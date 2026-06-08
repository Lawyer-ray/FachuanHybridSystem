vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('@/lib/date', () => ({
  formatDateOnly: vi.fn((d: string) => d || '-'),
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

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div><span>{label}</span><span>{String(value ?? '')}</span></div>
  ),
  DetailCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div><h3>{title}</h3>{children}</div>
  ),
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    ArrowLeft: Icon, Edit: Icon, Trash2: Icon, Copy: Icon, FileWarning: Icon,
    User: Icon, Building2: Icon, Briefcase: Icon, FileText: Icon, ExternalLink: Icon,
  }
})

vi.mock('framer-motion', () => ({
  motion: { div: (p: Record<string, unknown>) => <div {...p} /> },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../hooks/use-client', () => ({
  useClient: vi.fn(() => ({
    data: null,
    isLoading: false,
    error: null,
  })),
}))

vi.mock('../../hooks/use-client-mutations', () => ({
  useClientMutations: vi.fn(() => ({
    deleteClient: { mutateAsync: vi.fn(), isPending: false },
    createClient: { mutate: vi.fn(), isPending: false },
    updateClient: { mutate: vi.fn(), isPending: false },
  })),
}))

vi.mock('../../hooks/use-related-items', () => ({
  useRelatedItems: vi.fn(() => ({ data: null })),
}))

vi.mock('../../components/PropertyClueList', () => ({
  PropertyClueList: () => <div data-testid="property-clue-list">PropertyClueList</div>,
}))

vi.mock('../../components/IdentityDocManager', () => ({
  IdentityDocManager: () => <div data-testid="identity-doc-manager">IdentityDocManager</div>,
}))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CLIENTS: '/admin/clients' },
  generatePath: {
    clientEdit: (id: string) => `/admin/clients/${id}/edit`,
    caseDetail: (id: string) => `/admin/cases/${id}`,
    contractDetail: (id: string) => `/admin/contracts/${id}`,
  },
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { ClientDetail } from '../ClientDetail'
import { useClient } from '../../hooks/use-client'
import { useClientMutations } from '../../hooks/use-client-mutations'
import { useRelatedItems } from '../../hooks/use-related-items'

const mockClient = {
  id: 1,
  name: 'Wang',
  is_our_client: true,
  client_type: 'natural' as const,
  client_type_label: '自然人',
  phone: '13800138000',
  address: 'Beijing',
  id_number: '110101199001011234',
  legal_representative: null,
  legal_representative_id_number: null,
  identity_docs: [],
  created_at: '2024-01-01',
}

describe('ClientDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton when loading', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined, isLoading: true, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('renders error state when client not found', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined, isLoading: false, error: new Error('Not found'),
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('当事人不存在')).toBeInTheDocument()
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  it('renders client detail when loaded', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByRole('heading', { name: 'Wang' })).toBeInTheDocument()
    expect(screen.getByText('自然人')).toBeInTheDocument()
    expect(screen.getByText('我方当事人')).toBeInTheDocument()
  })

  it('renders action buttons', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
    expect(screen.getByText('复制')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  it('renders tabs for navigation', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    const tabs = screen.getAllByText('基本信息')
    expect(tabs.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('证件管理')).toBeInTheDocument()
    expect(screen.getByText('财产线索')).toBeInTheDocument()
    expect(screen.getByText('关联案件/合同')).toBeInTheDocument()
  })

  it('shows legal entity type badge for legal client', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, client_type: 'legal', client_type_label: '法人' },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('法人')).toBeInTheDocument()
  })

  it('shows legal representative for legal entity', () => {
    vi.mocked(useClient).mockReturnValue({
      data: {
        ...mockClient,
        client_type: 'legal',
        client_type_label: '法人',
        legal_representative: 'Li',
      },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('Li')).toBeInTheDocument()
  })

  it('shows empty related items messages', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    vi.mocked(useRelatedItems).mockReturnValue({
      data: { cases: [], contracts: [] },
    } as ReturnType<typeof useRelatedItems>)

    render(<ClientDetail clientId="1" />)
    // Click on related tab
    fireEvent.click(screen.getByText('关联案件/合同'))
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
    expect(screen.getByText('暂无关联合同')).toBeInTheDocument()
  })

  it('shows id number and phone in header', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    const idElements = screen.getAllByText('110101199001011234')
    expect(idElements.length).toBeGreaterThanOrEqual(1)
    const phoneElements = screen.getAllByText('13800138000')
    expect(phoneElements.length).toBeGreaterThanOrEqual(1)
  })
})
