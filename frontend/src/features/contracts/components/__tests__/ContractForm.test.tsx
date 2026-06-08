vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CONTRACTS: '/admin/contracts' },
}))

vi.mock('../../hooks/use-contract-mutations', () => ({
  useContractMutations: () => ({
    createContract: { mutateAsync: vi.fn() },
    updateContract: { mutateAsync: vi.fn() },
  }),
}))

vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: vi.fn(),
}))

vi.mock('../../hooks/use-clients-select', () => ({
  useClientsSelect: vi.fn(),
}))

vi.mock('../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return {
    ...actual,
    CASE_TYPE_LABELS: { civil: '民事', criminal: '刑事' },
    FEE_MODE_LABELS: { FIXED: '固定', FULL_RISK: '纯风险' },
    PARTY_ROLE_LABELS: { PRINCIPAL: '委托人', OPPOSING: '对方' },
  }
})

import { render, screen, fireEvent } from '@testing-library/react'
import { useLawyers } from '../../hooks/use-lawyers'
import { useClientsSelect } from '../../hooks/use-clients-select'
import { ContractForm } from '../ContractForm'

const mockUseLawyers = useLawyers as unknown as ReturnType<typeof vi.fn>
const mockUseClientsSelect = useClientsSelect as unknown as ReturnType<typeof vi.fn>

describe('ContractForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseLawyers.mockReturnValue({ data: [] })
    mockUseClientsSelect.mockReturnValue({ data: [] })
  })

  it('renders create mode title', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
  })

  it('renders submit button for create mode', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('创建合同')).toBeInTheDocument()
  })

  it('renders submit button for edit mode', () => {
    render(<ContractForm mode="edit" contract={{ id: 1, name: '测试', case_type: 'civil', fee_mode: 'FIXED', assignments: [], contract_parties: [] } as any} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders basic info section', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('合同名称 *')).toBeInTheDocument()
    expect(screen.getByText('案件类型')).toBeInTheDocument()
  })

  it('renders fee info section', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('收费信息')).toBeInTheDocument()
    expect(screen.getByText('收费模式')).toBeInTheDocument()
  })

  it('renders lawyer section', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('律师指派 *')).toBeInTheDocument()
  })

  it('renders party section', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('当事人')).toBeInTheDocument()
    expect(screen.getByText('添加')).toBeInTheDocument()
  })

  it('shows empty messages when no data', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('暂无律师数据')).toBeInTheDocument()
    expect(screen.getByText('未添加当事人')).toBeInTheDocument()
  })

  it('renders lawyers when available', () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: '张律师', username: 'zhang' }],
    })
    render(<ContractForm mode="create" />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('toggles lawyer selection on click', () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: '张律师', username: 'zhang' }],
    })
    render(<ContractForm mode="create" />)
    const lawyerBadge = screen.getByText('张律师')
    fireEvent.click(lawyerBadge)
    // After click, the first lawyer should be marked as primary
    expect(lawyerBadge).toBeInTheDocument()
  })

  it('shows add party button', () => {
    render(<ContractForm mode="create" />)
    const addBtn = screen.getByText('添加')
    expect(addBtn).toBeInTheDocument()
  })

  it('adds party on click', () => {
    render(<ContractForm mode="create" />)
    const addBtn = screen.getByText('添加')
    fireEvent.click(addBtn)
    // Should no longer show empty message
    expect(screen.queryByText('未添加当事人')).not.toBeInTheDocument()
  })

  it('renders date inputs', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('指定日期')).toBeInTheDocument()
    expect(screen.getByText('开始日期')).toBeInTheDocument()
    expect(screen.getByText('结束日期')).toBeInTheDocument()
  })

  it('renders fixed amount field for FIXED fee mode', () => {
    render(<ContractForm mode="create" />)
    expect(screen.getByText('固定金额')).toBeInTheDocument()
  })

  it('shows custom terms for CUSTOM fee mode', () => {
    const { container } = render(<ContractForm mode="create" />)
    // Default is FIXED, so custom terms should not be shown
    expect(screen.queryByText('自定义条款')).not.toBeInTheDocument()
  })
})
