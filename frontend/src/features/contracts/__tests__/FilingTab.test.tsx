import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { FilingTab } from '../components/FilingTab'

vi.mock('lucide-react', () => ({
  Briefcase: (props: Record<string, unknown>) => <svg data-testid="briefcase" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader" {...props} />,
  CheckCircle2: (props: Record<string, unknown>) => <svg data-testid="check-circle" {...props} />,
  XCircle: (props: Record<string, unknown>) => <svg data-testid="x-circle" {...props} />,
  AlertCircle: (props: Record<string, unknown>) => <svg data-testid="alert-circle" {...props} />,
  ExternalLink: (props: Record<string, unknown>) => <svg data-testid="external-link" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../api', () => ({
  contractApi: {
    fetchOAConfigs: vi.fn().mockResolvedValue([]),
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
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/shared', () => ({
  DetailCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div data-testid="detail-card">
      <h3>{title}</h3>
      {children}
    </div>
  ),
  DetailField: ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div data-testid="detail-field">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  ),
}))

const mockContract = {
  id: 1,
  cases: [{ id: 10, name: '合同纠纷', status_label: '进行中', current_stage_label: '一审' }],
  law_firm_oa_url: 'https://oa.example.com',
  law_firm_oa_case_number: 'OA-2024-001',
}

describe('FilingTab', () => {
  it('renders related cases section', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('关联案件')).toBeInTheDocument()
  })

  it('renders case name in related cases', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
  })

  it('renders OA system filing section', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('OA 系统立案')).toBeInTheDocument()
  })

  it('renders law firm OA section when URL exists', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('律所 OA')).toBeInTheDocument()
  })

  it('renders OA case number', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('OA-2024-001')).toBeInTheDocument()
  })

  it('renders empty state when no cases', () => {
    const emptyContract = { ...mockContract, cases: [], law_firm_oa_url: null, law_firm_oa_case_number: null }
    render(<MemoryRouter><FilingTab contract={emptyContract as never} /></MemoryRouter>)
    expect(screen.getByText('暂无关联案件')).toBeInTheDocument()
  })

  it('renders start filing button', () => {
    render(<MemoryRouter><FilingTab contract={mockContract as never} /></MemoryRouter>)
    expect(screen.getByText('开始立案')).toBeInTheDocument()
  })
})
