import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock dependencies before imports
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('lucide-react', () => {
  const icons = ['Shield', 'Loader2', 'Play', 'RefreshCw', 'Trash2', 'Link2', 'RotateCw', 'AlertCircle', 'Search']
  const mocks: Record<string, React.FC<Record<string, unknown>>> = {}
  for (const name of icons) {
    mocks[name] = (props) => <svg data-testid={`${name.toLowerCase()}-icon`} {...props} />
  }
  return mocks
})

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span data-testid="badge" {...props}>{children}</span>,
}))

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange, ...props }: Record<string, unknown>) => (
    <input
      type="checkbox"
      data-testid="checkbox"
      checked={!!checked}
      onChange={(e) => (onCheckedChange as (v: boolean) => void)?.(e.target.checked)}
      {...props}
    />
  ),
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div data-testid="alert-dialog">{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div data-testid="alert-content">{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/shared', () => ({
  DetailCard: ({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) => (
    <div data-testid="detail-card">
      <div data-testid="detail-card-title">
        {title} {extra}
      </div>
      {children}
    </div>
  ),
}))

const mockGetCourtGuaranteeInfo = vi.fn()
const mockGetCourtGuaranteeSession = vi.fn()
const mockEnsureGuaranteeQuote = vi.fn()
const mockExecuteCourtGuarantee = vi.fn()
const mockBindGuaranteeQuote = vi.fn()
const mockRetryGuaranteeQuote = vi.fn()
const mockDeleteGuaranteeQuote = vi.fn()

vi.mock('../api', () => ({
  caseApi: {
    getCourtGuaranteeInfo: (...args: unknown[]) => mockGetCourtGuaranteeInfo(...args),
    getCourtGuaranteeSession: (...args: unknown[]) => mockGetCourtGuaranteeSession(...args),
    ensureGuaranteeQuote: (...args: unknown[]) => mockEnsureGuaranteeQuote(...args),
    executeCourtGuarantee: (...args: unknown[]) => mockExecuteCourtGuarantee(...args),
    bindGuaranteeQuote: (...args: unknown[]) => mockBindGuaranteeQuote(...args),
    retryGuaranteeQuote: (...args: unknown[]) => mockRetryGuaranteeQuote(...args),
    deleteGuaranteeQuote: (...args: unknown[]) => mockDeleteGuaranteeQuote(...args),
  },
}))

import { CourtGuaranteeSection } from '../components/CourtGuaranteeSection'
import { toast } from 'sonner'

// Helper to set up a fresh mock for each test
function setupMocks(info: Record<string, unknown>) {
  mockGetCourtGuaranteeInfo.mockReturnValue(Promise.resolve(info))
  mockGetCourtGuaranteeSession.mockReturnValue(Promise.resolve({ status: 'completed', timing: null }))
  mockEnsureGuaranteeQuote.mockReturnValue(Promise.resolve({}))
  mockExecuteCourtGuarantee.mockReturnValue(Promise.resolve({ session_id: 's1', status: 'running', timing: null }))
  mockBindGuaranteeQuote.mockReturnValue(Promise.resolve({}))
  mockRetryGuaranteeQuote.mockReturnValue(Promise.resolve({}))
  mockDeleteGuaranteeQuote.mockReturnValue(Promise.resolve({}))
}

const baseInfo = {
  court_name: '北京市朝阳区人民法院',
  preserve_category: '财产保全',
  preserve_amount: '100000',
  insurance_company_name: '人保财险',
  consultant_code: 'C001',
  respondent_options: [
    { party_id: 1, name: '张三', legal_status_display: '被告' },
  ],
  quote_context: null,
}

const infoWithQuote = {
  ...baseInfo,
  quote_context: {
    quote_id: 100,
    status: 'completed',
    binding_id: null,
    items: [
      {
        id: 1,
        company_name: '担保公司A',
        min_amount: '500',
        max_amount: '1000',
        max_apply_amount: '500000000',
        is_recommended: true,
      },
    ],
  },
}

const infoWithBoundQuote = {
  ...baseInfo,
  quote_context: {
    quote_id: 100,
    status: 'completed',
    binding_id: 50,
    items: [],
  },
}

const infoWithMultipleRespondents = {
  ...baseInfo,
  respondent_options: [
    { party_id: 1, name: '张三', legal_status_display: '被告' },
    { party_id: 2, name: '李四', legal_status_display: '第三人' },
  ],
}

const infoWithoutAmount = {
  ...baseInfo,
  preserve_amount: null,
}

describe('CourtGuaranteeSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setupMocks(baseInfo)
  })

  it('renders detail card with title and loads case info on mount', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    expect(screen.getByTestId('detail-card-title')).toHaveTextContent('诉讼保全担保')
    await waitFor(() => {
      expect(mockGetCourtGuaranteeInfo).toHaveBeenCalledWith(1)
    })
    await waitFor(() => {
      expect(screen.getByText('北京市朝阳区人民法院')).toBeInTheDocument()
    })
  })

  it('shows warning when preserve_amount is missing', async () => {
    setupMocks(infoWithoutAmount)
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('未填写保全金额')).toBeInTheDocument()
    })
  })

  it('shows respondent selector when multiple respondents exist', async () => {
    setupMocks(infoWithMultipleRespondents)
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText(/被申请人/)).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText(/张三/)).toBeInTheDocument()
    })
    expect(screen.getByText(/李四/)).toBeInTheDocument()
  })

  it('renders quote table when quote items exist', async () => {
    setupMocks(infoWithQuote)
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('担保公司A')).toBeInTheDocument()
    })
    // formatQuoteRange('500', '1000') => '¥500 ~ ¥1000'
    expect(screen.getByText('¥500 ~ ¥1000')).toBeInTheDocument()
  })

  it('shows bound badge when quote is bound', async () => {
    setupMocks(infoWithBoundQuote)
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('已绑定')).toBeInTheDocument()
    })
  })

  it('handles ensureGuaranteeQuote call and shows toast', async () => {
    setupMocks(baseInfo)
    const user = userEvent.setup()
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('发起询价')).toBeInTheDocument()
    })
    await user.click(screen.getByText('发起询价'))
    await waitFor(() => {
      expect(mockEnsureGuaranteeQuote).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('询价已提交')
    })
  })

  it('handles execute call', async () => {
    setupMocks(infoWithQuote)
    const user = userEvent.setup()
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('开始申请')).toBeInTheDocument()
    })
    await user.click(screen.getByText('开始申请'))
    await waitFor(() => {
      expect(mockExecuteCourtGuarantee).toHaveBeenCalledWith(1)
    })
  })

  it('selects insurer from quote table row', async () => {
    setupMocks(infoWithQuote)
    const user = userEvent.setup()
    render(<CourtGuaranteeSection caseId={1} />)
    await waitFor(() => {
      expect(screen.getByText('担保公司A')).toBeInTheDocument()
    })
    const selectButton = screen.getByText('选用')
    await user.click(selectButton)
    expect(toast.success).toHaveBeenCalledWith('已选用 担保公司A')
  })
})
