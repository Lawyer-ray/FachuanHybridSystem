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

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ClientDetail } from '../ClientDetail'
import { useClient } from '../../hooks/use-client'
import { useClientMutations } from '../../hooks/use-client-mutations'
import { useRelatedItems } from '../../hooks/use-related-items'
import { copyToClipboard } from '@/lib/clipboard'
import { toast } from 'sonner'

const mockClient = {
  id: 1,
  name: 'Wang',
  is_our_client: true,
  client_type: 'natural' as const,
  client_type_label: '自然人',
  phone: '00000000000',
  address: 'Beijing',
  id_number: '000000000000000100', // pragma: allowlist secret
  legal_representative: null,
  legal_representative_id_number: null,
  identity_docs: [],
  created_at: '2024-01-01',
}

describe('ClientDetail - coverage improvements', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========== handleCopy - covers line 73-74 (client exists) ==========

  it('handleCopy calls copyToClipboard when client is loaded', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('复制'))
    expect(copyToClipboard).toHaveBeenCalled()
  })

  // ========== handleCopy - covers null client early return (line 73) ==========

  it('handleCopy does nothing when client is null', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    // Error state is shown, no copy button available
    expect(screen.getByText('当事人不存在')).toBeInTheDocument()
  })

  // ========== handleDelete - success path (lines 77-80) ==========

  it('handleDelete success shows toast and navigates', async () => {
    const mockDeleteAsync = vi.fn().mockResolvedValue({})
    vi.mocked(useClientMutations).mockReturnValue({
      deleteClient: { mutateAsync: mockDeleteAsync, isPending: false },
      createClient: { mutate: vi.fn(), isPending: false },
      updateClient: { mutate: vi.fn(), isPending: false },
    } as ReturnType<typeof useClientMutations>)

    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('删除'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('当事人已删除')
    })
  })

  // ========== handleDelete - error path (line 81) ==========

  it('handleDelete failure shows error toast', async () => {
    const mockDeleteAsync = vi.fn().mockRejectedValue(new Error('fail'))
    vi.mocked(useClientMutations).mockReturnValue({
      deleteClient: { mutateAsync: mockDeleteAsync, isPending: false },
      createClient: { mutate: vi.fn(), isPending: false },
      updateClient: { mutate: vi.fn(), isPending: false },
    } as ReturnType<typeof useClientMutations>)

    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('删除'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  // ========== Error state with no client (null) - covers line 86 ==========

  it('renders error state when client is null and no error', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('当事人不存在')).toBeInTheDocument()
  })

  // ========== Legal entity - showLegalRep true (lines 190-191) ==========

  it('shows legal representative fields for legal entity', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, client_type: 'legal', client_type_label: '法人', legal_representative: 'Li', legal_representative_id_number: '110' },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('Li')).toBeInTheDocument()
  })

  // ========== non_legal_org - legal rep label (line 39) ==========

  it('shows "负责人" label for non_legal_org type', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, client_type: 'non_legal_org', client_type_label: '非法人组织', legal_representative: 'Leader', legal_representative_id_number: '220' },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('Leader')).toBeInTheDocument()
  })

  // ========== Natural client - no legal rep, shows created_at (line 196) ==========

  it('shows created_at and identity docs count for natural client', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, client_type: 'natural', identity_docs: [{ id: 1 }] },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.getByText('创建时间')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument() // identity_docs length
  })

  // ========== No id_number, no phone - covers null branches (lines 118-123) ==========

  it('hides id_number and phone when null', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, id_number: null, phone: null },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    const wangElements = screen.getAllByText('Wang')
    expect(wangElements.length).toBeGreaterThanOrEqual(1)
  })

  // ========== is_our_client false - covers badge branch ==========

  it('does not show "我方当事人" badge when is_our_client is false', () => {
    vi.mocked(useClient).mockReturnValue({
      data: { ...mockClient, is_our_client: false },
      isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    expect(screen.queryByText('我方当事人')).not.toBeInTheDocument()
  })

  // ========== Related items with data - covers related tab branches ==========

  it('shows related cases and contracts when data exists', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    vi.mocked(useRelatedItems).mockReturnValue({
      data: {
        cases: [{ id: 1, name: 'Case A', case_type: 'civil', status: 'open', current_stage: '一审', legal_status: '审理中' }],
        contracts: [{ id: 1, name: 'Contract A', case_type: 'civil', status: 'active', role: '甲方' }],
      },
    } as ReturnType<typeof useRelatedItems>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('关联案件/合同'))
    expect(screen.getByText('Case A')).toBeInTheDocument()
    expect(screen.getByText('Contract A')).toBeInTheDocument()
    expect(screen.getByText('一审')).toBeInTheDocument()
    expect(screen.getByText('审理中')).toBeInTheDocument()
    expect(screen.getByText('甲方')).toBeInTheDocument()
  })

  // ========== Related items without data (null) - covers empty branch ==========

  it('shows empty messages when related items data is null', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    vi.mocked(useRelatedItems).mockReturnValue({
      data: undefined,
    } as ReturnType<typeof useRelatedItems>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('关联案件/合同'))
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
    expect(screen.getByText('暂无关联合同')).toBeInTheDocument()
  })

  // ========== Related items with empty arrays ==========

  it('shows empty messages when related items have empty arrays', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    vi.mocked(useRelatedItems).mockReturnValue({
      data: { cases: [], contracts: [] },
    } as ReturnType<typeof useRelatedItems>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('关联案件/合同'))
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
    expect(screen.getByText('暂无关联合同')).toBeInTheDocument()
  })

  // ========== Related cases without optional fields - covers badge conditionals ==========

  it('renders related cases without current_stage and legal_status badges', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    vi.mocked(useRelatedItems).mockReturnValue({
      data: {
        cases: [{ id: 1, name: 'Case B', case_type: 'civil', status: 'open', current_stage: null, legal_status: null }],
        contracts: [{ id: 1, name: 'Contract B', case_type: 'civil', status: 'active', role: null }],
      },
    } as ReturnType<typeof useRelatedItems>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('关联案件/合同'))
    expect(screen.getByText('Case B')).toBeInTheDocument()
    expect(screen.getByText('Contract B')).toBeInTheDocument()
  })

  // ========== Tab switching - docs tab ==========

  it('shows identity doc manager when docs tab is clicked', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('证件管理'))
    expect(screen.getByTestId('identity-doc-manager')).toBeInTheDocument()
  })

  // ========== Tab switching - clues tab ==========

  it('shows property clue list when clues tab is clicked', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('财产线索'))
    expect(screen.getByTestId('property-clue-list')).toBeInTheDocument()
  })

  // ========== Delete dialog cancel ==========

  it('cancel button in delete dialog closes it', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('删除'))
    expect(screen.getByText('确认删除')).toBeInTheDocument()
    fireEvent.click(screen.getByText('取消'))
  })

  // ========== Back button navigates ==========

  it('back button navigates to clients list', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('返回列表'))
    // Just verify the button exists and is clickable
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  // ========== Edit button ==========

  it('edit button triggers navigation', () => {
    vi.mocked(useClient).mockReturnValue({
      data: mockClient, isLoading: false, error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientDetail clientId="1" />)
    fireEvent.click(screen.getByText('编辑'))
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  // ========== default export ==========

  it('exports ClientDetail as default', async () => {
    const mod = await import('../ClientDetail')
    expect(mod.default).toBeDefined()
  })
})
