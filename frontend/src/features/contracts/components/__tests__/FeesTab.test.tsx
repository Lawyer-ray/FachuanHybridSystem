vi.mock('../../api', () => ({
  contractApi: { deleteClientPaymentRecord: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (path: string) => path,
  api: {},
  createFeatureApiClient: vi.fn(),
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

vi.mock('../PaymentList', () => ({
  PaymentList: () => <div data-testid="payment-list" />,
}))

vi.mock('../../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../types')>()
  return {
    ...actual,
    FEE_MODE_LABELS: { FIXED: '固定收费', FULL_RISK: '纯风险', SEMI_RISK: '半风险', CUSTOM: '自定义' },
  }
})

import { render, screen } from '@testing-library/react'
import { FeesTab } from '../FeesTab'

describe('FeesTab', () => {
  const baseContract = {
    id: 1,
    name: '测试合同',
    fee_mode: 'FIXED',
    fixed_amount: 100000,
    risk_rate: null,
    custom_terms: null,
    total_received: 50000,
    total_invoiced: 30000,
    unpaid_amount: 50000,
    payments: [],
    client_payment_records: [],
  } as any

  it('renders fee terms section', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('收费条款')).toBeInTheDocument()
    expect(screen.getByText('收费模式')).toBeInTheDocument()
  })

  it('shows fee mode label', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('固定收费')).toBeInTheDocument()
  })

  it('shows fixed amount', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('¥100000')).toBeInTheDocument()
  })

  it('shows risk rate when present', () => {
    const contract = { ...baseContract, fee_mode: 'FULL_RISK', fixed_amount: null, risk_rate: 15 }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('15%')).toBeInTheDocument()
  })

  it('shows custom terms when present', () => {
    const contract = { ...baseContract, fee_mode: 'CUSTOM', custom_terms: '自定义条款内容' }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('自定义条款内容')).toBeInTheDocument()
  })

  it('renders progress section', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getAllByText('收款进度').length).toBeGreaterThan(0)
    expect(screen.getAllByText('开票进度').length).toBeGreaterThan(0)
  })

  it('shows payment percent', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows 100% when fully paid', () => {
    const contract = { ...baseContract, total_received: 100000 }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('已收齐')).toBeInTheDocument()
  })

  it('shows unpaid amount when present', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText(/未收/)).toBeInTheDocument()
  })

  it('shows invoice progress', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('60%')).toBeInTheDocument()
  })

  it('shows pending invoice badge', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('待开票')).toBeInTheDocument()
  })

  it('renders payment list', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByTestId('payment-list')).toBeInTheDocument()
  })

  it('renders client payment section', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getByText('客户付款凭证')).toBeInTheDocument()
    expect(screen.getByText('暂无客户付款凭证')).toBeInTheDocument()
  })

  it('shows client payment records', () => {
    const contract = {
      ...baseContract,
      client_payment_records: [
        { id: 1, amount: 5000, note: '转账', created_at: '2026-01-01', image_path: null },
      ],
    }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('¥5000')).toBeInTheDocument()
    expect(screen.getByText('转账')).toBeInTheDocument()
  })

  it('does not show invoice section when no invoices', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.queryByText('发票记录')).not.toBeInTheDocument()
  })

  it('shows invoice section when invoices exist', () => {
    const contract = {
      ...baseContract,
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [
            { id: 1, original_filename: '发票1.pdf', invoice_number: 'INV-001', total_amount: 10000, uploaded_at: '2026-01-15', paymentAmount: 10000 },
          ],
        },
      ],
    }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
  })

  it('shows 0% when no fixed amount', () => {
    const contract = { ...baseContract, fixed_amount: null }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('shows received amounts', () => {
    render(<FeesTab contract={baseContract} />)
    expect(screen.getAllByText(/已收 ¥50000/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/已开票 ¥30000/).length).toBeGreaterThan(0)
  })

  // --- Additional tests from coverage expansion ---

  it('falls back to raw fee_mode for unknown mode', () => {
    render(<FeesTab contract={{ ...baseContract, fee_mode: 'UNKNOWN' } as any} />)
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
  })

  it('hides fixed amount when null', () => {
    render(<FeesTab contract={{ ...baseContract, fixed_amount: null } as any} />)
    expect(screen.queryByText('固定/前期律师费')).not.toBeInTheDocument()
  })

  it('hides risk rate when null', () => {
    render(<FeesTab contract={{ ...baseContract, risk_rate: null } as any} />)
    expect(screen.queryByText('风险比例')).not.toBeInTheDocument()
  })

  it('hides custom terms when null', () => {
    render(<FeesTab contract={{ ...baseContract, custom_terms: null } as any} />)
    expect(screen.queryByText('自定义条款')).not.toBeInTheDocument()
  })

  it('hides unpaid amount when null', () => {
    render(<FeesTab contract={{ ...baseContract, unpaid_amount: null } as any} />)
    expect(screen.queryByText(/未收/)).not.toBeInTheDocument()
  })

  it('hides unpaid amount when 0', () => {
    render(<FeesTab contract={{ ...baseContract, unpaid_amount: 0 } as any} />)
    expect(screen.queryByText(/未收/)).not.toBeInTheDocument()
  })

  it('shows dash when no fixed amount for receivable', () => {
    render(<FeesTab contract={{ ...baseContract, fixed_amount: null, total_received: 0 } as any} />)
    expect(screen.getByText('应收 —')).toBeInTheDocument()
  })

  it('calculates invoice percent correctly', () => {
    render(<FeesTab contract={{ ...baseContract, total_received: 100000, total_invoiced: 50000 } as any} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('hides "待开票" when invoice >= 100%', () => {
    render(<FeesTab contract={{ ...baseContract, total_received: 100000, total_invoiced: 100000 } as any} />)
    expect(screen.queryByText('待开票')).not.toBeInTheDocument()
  })

  it('hides "待开票" when received = 0', () => {
    render(<FeesTab contract={{ ...baseContract, total_received: 0, total_invoiced: 0 } as any} />)
    expect(screen.queryByText('待开票')).not.toBeInTheDocument()
  })

  it('renders invoices without invoice_number', () => {
    const contract = {
      ...baseContract,
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: null, uploaded_at: null }],
        },
      ],
    }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
  })

  it('renders invoice with uploaded_at', () => {
    const contract = {
      ...baseContract,
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: 5000, uploaded_at: '2024-06-01' }],
        },
      ],
    }
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
  })

  it('renders client payment with image_path link', () => {
    const contract = {
      ...baseContract,
      client_payment_records: [
        { id: 1, amount: 1000, note: '', created_at: '2024-01-01', image_path: '/img/receipt.jpg' },
      ],
    }
    render(<FeesTab contract={contract} />)
    // The image icon is rendered as a link when image_path exists
    const link = document.querySelector('a[href*="receipt.jpg"]')
    expect(link).toBeInTheDocument()
  })

  it('renders payment percent capped at 100', () => {
    render(<FeesTab contract={{ ...baseContract, fixed_amount: 100, total_received: 200 } as any} />)
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0)
  })
})
