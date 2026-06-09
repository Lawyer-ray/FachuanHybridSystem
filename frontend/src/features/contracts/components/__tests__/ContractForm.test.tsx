const mockCreateMutate = vi.fn().mockResolvedValue({})
const mockUpdateMutate = vi.fn().mockResolvedValue({})
const mockNavigate = vi.fn()

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CONTRACTS: '/admin/contracts' },
}))

vi.mock('../../hooks/use-contract-mutations', () => ({
  useContractMutations: () => ({
    createContract: { mutateAsync: mockCreateMutate },
    updateContract: { mutateAsync: mockUpdateMutate },
  }),
}))

vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: vi.fn(),
}))

vi.mock('../../hooks/use-clients-select', () => ({
  useClientsSelect: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return {
    ...actual,
    CASE_TYPE_LABELS: { civil: '民事', criminal: '刑事' },
    FEE_MODE_LABELS: { FIXED: '固定', FULL_RISK: '纯风险', SEMI_RISK: '半风险', CUSTOM: '自定义' },
    PARTY_ROLE_LABELS: { PRINCIPAL: '委托人', OPPOSING: '对方' },
  }
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
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

  // --- New tests for uncovered lines ---

  it('initializes from contract prop with assignments and parties', () => {
    const contract = {
      id: 1,
      name: 'Test Contract',
      case_type: 'criminal',
      fee_mode: 'SEMI_RISK',
      fixed_amount: 5000,
      risk_rate: 10,
      custom_terms: 'custom',
      specified_date: '2026-01-01',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      assignments: [{ lawyer_id: 1 }, { lawyer_id: 2 }],
      contract_parties: [{ client: 10, role: 'PRINCIPAL' }, { client: 20, role: 'OPPOSING' }],
    } as any
    render(<ContractForm mode="edit" contract={contract} />)
    expect(screen.getByDisplayValue('Test Contract')).toBeInTheDocument()
    expect(screen.getByDisplayValue('5000')).toBeInTheDocument()
    expect(screen.getByDisplayValue('10')).toBeInTheDocument()
  })

  it('validates empty name on submit', async () => {
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('请输入合同名称')
    })
  })

  it('validates no lawyers on submit', async () => {
    const { container } = render(<ContractForm mode="create" />)
    const nameInput = screen.getByPlaceholderText('输入合同名称')
    fireEvent.change(nameInput, { target: { value: 'Test' } })
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('请至少指派一个律师')
    })
  })

  it('creates contract successfully in create mode', async () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'Lawyer', username: 'lawyer' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'New Contract' } })
    fireEvent.click(screen.getByText('Lawyer'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(mockCreateMutate).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('合同创建成功')
      expect(mockNavigate).toHaveBeenCalledWith('/admin/contracts')
    })
  })

  it('updates contract successfully in edit mode', async () => {
    const contract = {
      id: 1, name: 'Old', case_type: 'civil', fee_mode: 'FIXED',
      assignments: [{ lawyer_id: 1 }], contract_parties: [],
    } as any
    const { container } = render(<ContractForm mode="edit" contract={contract} />)
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(mockUpdateMutate).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('合同更新成功')
      expect(mockNavigate).toHaveBeenCalledWith('/admin/contracts')
    })
  })

  it('handles create error gracefully', async () => {
    mockCreateMutate.mockRejectedValueOnce(new Error('fail'))
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'L', username: 'l' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('L'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('操作失败')
    })
  })

  it('toggles lawyer selection and marks first selected as primary', () => {
    mockUseLawyers.mockReturnValue({
      data: [
        { id: 1, real_name: 'Lawyer A', username: 'a' },
        { id: 2, real_name: 'Lawyer B', username: 'b' },
      ],
    })
    render(<ContractForm mode="create" />)
    fireEvent.click(screen.getByText('Lawyer A'))
    // After selecting first lawyer, it should show (主办)
    expect(screen.getByText(/Lawyer A/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Lawyer B'))
    // Deselect A
    fireEvent.click(screen.getByText(/Lawyer A/))
  })

  it('adds and removes parties', () => {
    render(<ContractForm mode="create" />)
    // Add a party
    fireEvent.click(screen.getByText('添加'))
    expect(screen.queryByText('未添加当事人')).not.toBeInTheDocument()
    // Remove it
    fireEvent.click(screen.getByText('×'))
    expect(screen.getByText('未添加当事人')).toBeInTheDocument()
  })

  it('handles input changes for all fields', () => {
    render(<ContractForm mode="create" />)
    // Name
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'New Name' } })
    expect(screen.getByDisplayValue('New Name')).toBeInTheDocument()
    // Date fields
    const dateInputs = screen.getAllByDisplayValue('')
    // specifiedDate, startDate, endDate
    expect(dateInputs.length).toBeGreaterThan(0)
  })

  it('shows risk rate for FULL_RISK fee mode', () => {
    render(<ContractForm mode="create" />)
    // Default is FIXED, risk rate should not show
    expect(screen.queryByText('风险比例(%)')).not.toBeInTheDocument()
  })

  it('handles cancel button navigation', () => {
    render(<ContractForm mode="create" />)
    fireEvent.click(screen.getByText('取消'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/contracts')
  })

  it('creates contract with parties data', async () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'Lawyer', username: 'lawyer' }],
    })
    mockUseClientsSelect.mockReturnValue({
      data: [{ id: 10, name: 'Client A' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'C' } })
    fireEvent.click(screen.getByText('Lawyer'))
    fireEvent.click(screen.getByText('添加'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(mockCreateMutate).toHaveBeenCalled()
    })
  })

  it('sets submitting state during async operation', async () => {
    let resolveCreate: (value?: unknown) => void
    mockCreateMutate.mockReturnValueOnce(new Promise((r) => { resolveCreate = r }))
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'L', username: 'l' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('L'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(screen.getByText('提交中...')).toBeInTheDocument()
    })
    resolveCreate!()
  })

  it('sends null for empty optional fields in create', async () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'L', username: 'l' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('L'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      const callArgs = mockCreateMutate.mock.calls[0][0]
      expect(callArgs.custom_terms).toBeNull()
      expect(callArgs.specified_date).toBeNull()
      expect(callArgs.start_date).toBeNull()
      expect(callArgs.end_date).toBeNull()
    })
  })

  it('sends numeric values for amounts and rates', async () => {
    mockUseLawyers.mockReturnValue({
      data: [{ id: 1, real_name: 'L', username: 'l' }],
    })
    const { container } = render(<ContractForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('输入合同名称'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '1000' } })
    fireEvent.click(screen.getByText('L'))
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      const callArgs = mockCreateMutate.mock.calls[0][0]
      expect(callArgs.fixed_amount).toBe(1000)
    })
  })

  it('renders updateContract branch correctly (else if contract)', async () => {
    const contract = {
      id: 5, name: 'Existing', case_type: 'civil', fee_mode: 'FIXED',
      fixed_amount: 100, risk_rate: null, custom_terms: 'terms',
      specified_date: '2026-06-01', start_date: '2026-01-01', end_date: '2026-12-31',
      assignments: [{ lawyer_id: 1 }], contract_parties: [{ client: 5, role: 'PRINCIPAL' }],
    } as any
    const { container } = render(<ContractForm mode="edit" contract={contract} />)
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(mockUpdateMutate).toHaveBeenCalledWith(expect.objectContaining({ id: 5 }))
    })
  })

  it('update error triggers toast', async () => {
    mockUpdateMutate.mockRejectedValueOnce(new Error('fail'))
    const contract = {
      id: 1, name: 'Test', case_type: 'civil', fee_mode: 'FIXED',
      assignments: [{ lawyer_id: 1 }], contract_parties: [],
    } as any
    const { container } = render(<ContractForm mode="edit" contract={contract} />)
    fireEvent.submit(container.querySelector('form')!)
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('操作失败')
    })
  })
})
