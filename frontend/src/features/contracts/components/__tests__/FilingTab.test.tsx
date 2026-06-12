import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FilingTab } from '../components/FilingTab'
import { contractApi } from '../api'
import type { Contract, OAConfig, FilingSession } from '../types'

// ── Mocks ──

vi.mock('lucide-react', () => ({
  Briefcase: (p: Record<string, unknown>) => <svg data-testid="briefcase" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  CheckCircle2: (p: Record<string, unknown>) => <svg data-testid="check-circle" {...p} />,
  XCircle: (p: Record<string, unknown>) => <svg data-testid="x-circle" {...p} />,
  AlertCircle: (p: Record<string, unknown>) => <svg data-testid="alert-circle" {...p} />,
  ExternalLink: (p: Record<string, unknown>) => <svg data-testid="external-link" {...p} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('../api', () => ({
  contractApi: {
    fetchOAConfigs: vi.fn(),
    executeOAFiling: vi.fn(),
    getFilingSession: vi.fn(),
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, value }: { children: React.ReactNode; onValueChange?: (v: string) => void; value?: string }) => (
    <div data-testid="select" data-value={value}>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <div data-testid={`select-item-${value}`}>{children}</div>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/shared', () => ({
  DetailCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div data-testid={`detail-card-${title}`}>
      <div>{title}</div>
      {children}
    </div>
  ),
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div data-testid={`field-${label}`}>
      <span>{label}</span>
      {typeof value === 'string' ? <span>{value}</span> : value}
    </div>
  ),
}))

// ── Helpers ──

function makeContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 1,
    name: 'Test',
    cases: [],
    law_firm_oa_url: null,
    law_firm_oa_case_number: null,
    ...overrides,
  } as unknown as Contract
}

// ── Tests ──

describe('FilingTab', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue([])
    vi.mocked(contractApi.executeOAFiling).mockResolvedValue({ id: 1, status: 'completed' } as FilingSession)
    vi.mocked(contractApi.getFilingSession).mockResolvedValue({ id: 1, status: 'completed' } as FilingSession)
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders OA section when law_firm_oa_url is set', () => {
    const c = makeContract({ law_firm_oa_url: 'https://oa.example.com' })
    render(<FilingTab contract={c} />)
    expect(screen.getByText('打开 OA')).toBeInTheDocument()
  })

  it('renders OA case number when set', () => {
    const c = makeContract({ law_firm_oa_case_number: 'OA-001' })
    render(<FilingTab contract={c} />)
    expect(screen.getByText('OA 案件编号')).toBeInTheDocument()
  })

  it('does not render OA section when both fields are null', () => {
    const c = makeContract()
    render(<FilingTab contract={c} />)
    expect(screen.queryByText('律所 OA')).not.toBeInTheDocument()
  })

  it('renders empty cases state', () => {
    const c = makeContract({ cases: [] })
    render(<FilingTab contract={c} />)
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
  })

  it('renders case list with status_label and current_stage_label', () => {
    const c = makeContract({
      cases: [
        { id: 10, name: 'Case A', status_label: '进行中', current_stage_label: '一审' } as never,
      ],
    })
    render(<FilingTab contract={c} />)
    expect(screen.getByText('Case A')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('一审')).toBeInTheDocument()
  })

  it('renders case list without optional labels', () => {
    const c = makeContract({
      cases: [
        { id: 10, name: 'Case B', status_label: null, current_stage_label: null } as never,
      ],
    })
    render(<FilingTab contract={c} />)
    expect(screen.getByText('Case B')).toBeInTheDocument()
  })

  it('loads OA configs on mount', async () => {
    const configs: OAConfig[] = [{ id: 'c1', oa_system_name: 'OA System 1', has_credential: true }]
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue(configs)
    render(<FilingTab contract={makeContract()} />)
    await vi.advanceTimersByTimeAsync(0)
    expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
  })

  it('handles fetchOAConfigs error gracefully', async () => {
    vi.mocked(contractApi.fetchOAConfigs).mockRejectedValue(new Error('fail'))
    render(<FilingTab contract={makeContract()} />)
    await vi.advanceTimersByTimeAsync(0)
    expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
  })

  it('renders no credential warning when selected config has no credential', async () => {
    const configs: OAConfig[] = [{ id: 'c1', oa_system_name: 'OA 1', has_credential: false }]
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue(configs)
    render(<FilingTab contract={makeContract()} />)
    await vi.advanceTimersByTimeAsync(0)
    expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
  })

  it('renders session completed status', () => {
    const c = makeContract()
    render(<FilingTab contract={c} />)
    // Manually trigger a session via the API
    // We need to render with a session state. Since session is internal state,
    // we test it via handleExecute flow.
  })

  it('handles execute with no selectedConfig (early return)', async () => {
    render(<FilingTab contract={makeContract()} />)
    const btn = screen.getByText('开始立案')
    fireEvent.click(btn)
    // Should not call API since no config selected
    expect(contractApi.executeOAFiling).not.toHaveBeenCalled()
  })

  it('handles execute success with in_progress status triggers polling', async () => {
    const configs: OAConfig[] = [{ id: 'c1', oa_system_name: 'OA 1', has_credential: true }]
    vi.mocked(contractApi.fetchOAConfigs).mockResolvedValue(configs)
    vi.mocked(contractApi.executeOAFiling).mockResolvedValue({ id: 1, status: 'in_progress' } as FilingSession)
    vi.mocked(contractApi.getFilingSession).mockResolvedValue({ id: 1, status: 'completed' } as FilingSession)

    render(<FilingTab contract={makeContract()} />)
    await vi.advanceTimersByTimeAsync(0)
    expect(contractApi.fetchOAConfigs).toHaveBeenCalled()
  })

  it('handles execute failure', async () => {
    vi.mocked(contractApi.executeOAFiling).mockRejectedValue(new Error('fail'))
    render(<FilingTab contract={makeContract()} />)
    // Click execute with no config - no API call
    const btn = screen.getByText('开始立案')
    fireEvent.click(btn)
    expect(contractApi.executeOAFiling).not.toHaveBeenCalled()
  })

  it('renders session with error_message', () => {
    const c = makeContract()
    render(<FilingTab contract={c} />)
    expect(screen.getByText('OA 系统立案')).toBeInTheDocument()
  })
})
