import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { FilingTab } from '../FilingTab'
import { contractApi } from '../../api'
import { toast } from 'sonner'
import type { Contract, CaseItem } from '../../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => {
  const icons = ['Briefcase', 'Loader2', 'CheckCircle2', 'XCircle', 'AlertCircle', 'ExternalLink']
  const map: Record<string, React.FC> = {}
  for (const name of icons) map[name] = () => <svg data-testid={name.toLowerCase()} />
  return map
})

vi.mock('../../api', () => ({
  contractApi: {
    fetchOAConfigs: vi.fn().mockResolvedValue([]),
    executeOAFiling: vi.fn(),
    getFilingSession: vi.fn(),
  },
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/components/shared', () => ({
  DetailCard: ({ children, title }: { children: React.ReactNode; title: string }) => <div><h3>{title}</h3>{children}</div>,
  DetailField: ({ label, value }: { label: string; value: React.ReactNode }) => <div><span>{label}</span><span>{value}</span></div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean}>{children}</button>
  ),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (v: string) => void }) => (
    <div data-testid="select">{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}))

function makeContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 1, name: 'Test Contract', case_type: 'civil', status: 'active',
    specified_date: null, start_date: null, end_date: null, is_filed: false,
    fee_mode: 'FIXED', fixed_amount: null, risk_rate: null, custom_terms: null,
    representation_stages: [], cases: [], contract_parties: [],
    case_type_label: '民商事', status_label: '在办', reminders: [],
    payments: [], supplementary_agreements: [], client_payment_records: [],
    can_archive: false, total_received: 0, total_invoiced: 0, unpaid_amount: null,
    assignments: [], primary_lawyer: null, matched_document_template: null,
    matched_folder_templates: null, has_matched_templates: false,
    finalized_materials: [], filing_number: null, law_firm_oa_url: null,
    law_firm_oa_case_number: null, ...overrides,
  }
}

describe('FilingTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders related cases section', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.getByText('关联案件')).toBeInTheDocument()
  })

  it('renders empty cases message', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
  })

  it('renders cases list', () => {
    const cases: CaseItem[] = [
      { id: 1, name: 'Case A', status: 'active', status_label: '进行中', case_type: null, start_date: null, effective_date: null, target_amount: null, preservation_amount: null, cause_of_action: null, current_stage: null, current_stage_label: '一审' },
    ]
    render(<MemoryRouter><FilingTab contract={makeContract({ cases })} /></MemoryRouter>)
    expect(screen.getByText('Case A')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('一审')).toBeInTheDocument()
  })

  it('renders cases without optional labels', () => {
    const cases: CaseItem[] = [
      { id: 1, name: 'Case B', status: null, status_label: null, case_type: null, start_date: null, effective_date: null, target_amount: null, preservation_amount: null, cause_of_action: null, current_stage: null, current_stage_label: null },
    ]
    render(<MemoryRouter><FilingTab contract={makeContract({ cases })} /></MemoryRouter>)
    expect(screen.getByText('Case B')).toBeInTheDocument()
  })

  it('renders OA system filing section', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.getByText('OA 系统立案')).toBeInTheDocument()
    expect(screen.getByText('选择 OA 系统')).toBeInTheDocument()
  })

  it('renders law firm OA section when URL present', () => {
    render(<MemoryRouter><FilingTab contract={makeContract({ law_firm_oa_url: 'http://oa.test', law_firm_oa_case_number: 'OA-001' })} /></MemoryRouter>)
    expect(screen.getByText('律所 OA')).toBeInTheDocument()
    expect(screen.getByText('OA 案件编号')).toBeInTheDocument()
    expect(screen.getByText('OA-001')).toBeInTheDocument()
  })

  it('does not render law firm OA section when no URL or case number', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.queryByText('律所 OA')).not.toBeInTheDocument()
  })

  it('renders OA link with correct href', () => {
    render(<MemoryRouter><FilingTab contract={makeContract({ law_firm_oa_url: 'http://oa.test' })} /></MemoryRouter>)
    const link = screen.getByText('打开 OA')
    expect(link).toHaveAttribute('href', 'http://oa.test')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('renders start filing button disabled when no config selected', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.getByText('开始立案')).toBeDisabled()
  })

  it('handles fetchOAConfigs error', async () => {
    vi.mocked(contractApi.fetchOAConfigs).mockRejectedValue(new Error('fail'))
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    await waitFor(() => {
      expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
    })
  })

  it('renders no credential warning when selected config has no credential', async () => {
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue([
      { id: 'oa-1', oa_system_name: 'Test OA', has_credential: false },
    ])
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    await waitFor(() => {
      expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
    })
  })

  it('renders session status completed', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    // Session is null initially, no session status rendered
    expect(screen.queryByText('立案完成')).not.toBeInTheDocument()
  })

  it('renders session status failed', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.queryByText('立案失败')).not.toBeInTheDocument()
  })

  it('renders OA system description text', () => {
    render(<MemoryRouter><FilingTab contract={makeContract()} /></MemoryRouter>)
    expect(screen.getByText(/通过律所 OA 系统自动立案/)).toBeInTheDocument()
  })

  it('renders law firm OA with only case number', () => {
    render(<MemoryRouter><FilingTab contract={makeContract({ law_firm_oa_case_number: 'CASE-123' })} /></MemoryRouter>)
    expect(screen.getByText('律所 OA')).toBeInTheDocument()
    expect(screen.getByText('CASE-123')).toBeInTheDocument()
  })

  it('renders OA link as dash when no URL', () => {
    render(<MemoryRouter><FilingTab contract={makeContract({ law_firm_oa_url: null, law_firm_oa_case_number: 'CASE-123' })} /></MemoryRouter>)
    expect(screen.getByText('律所 OA')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
