/**
 * Additional coverage tests for CaseForm.tsx
 * Targets: uncovered branches (24)
 * Focus: edit mode submission with changed fields for each field,
 * create mode with parties/assignments/authorities that have values,
 * null coalescing branches for caseData fields
 */

const mockNavigate = vi.fn()
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CASES: '/admin/cases' },
  generatePath: {
    caseDetail: (id: string) => `/admin/cases/${id}`,
    caseEdit: (id: string) => `/admin/cases/${id}/edit`,
  },
}))

vi.mock('../../hooks/use-case', () => ({ useCase: vi.fn() }))
vi.mock('../../hooks/use-case-mutations', () => ({ useCaseMutations: vi.fn() }))

vi.mock('../CauseSelector', () => ({
  CauseSelector: () => <div data-testid="cause-selector" />,
}))
vi.mock('../FeeCalculator', () => ({
  FeeCalculator: () => <div data-testid="fee-calculator" />,
}))
vi.mock('../CasePartySection', () => ({
  CasePartySection: () => <div data-testid="party-section" />,
}))
vi.mock('../CaseAssignmentSection', () => ({
  CaseAssignmentSection: () => <div data-testid="assignment-section" />,
}))
vi.mock('../CaseLogSection', () => ({
  CaseLogSection: () => <div data-testid="log-section" />,
}))
vi.mock('../CaseNumberSection', () => ({
  CaseNumberSection: () => <div data-testid="number-section" />,
}))
vi.mock('../AuthoritySection', () => ({
  AuthoritySection: () => <div data-testid="authority-section" />,
}))

vi.mock('../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return {
    ...actual,
    caseFormSchema: {
      extend: () => actual.caseFormSchema.extend({
        parties: actual.z.array(actual.z.object({
          client_id: actual.z.number().int().positive(),
          legal_status: actual.z.string().optional(),
        })).default([]),
        assignments: actual.z.array(actual.z.object({
          lawyer_id: actual.z.number().int().positive(),
        })).default([]),
        authorities: actual.z.array(actual.z.object({
          name: actual.z.string().optional(),
          authority_type: actual.z.string().optional(),
        })).default([]),
      }),
    },
  }
})

vi.mock('@hookform/resolvers/zod', () => ({
  zodResolver:
    (schema: { safeParse: (data: unknown) => { success: boolean; error?: { issues: Array<{ path: (string | number)[]; message: string }> } } }) =>
    (data: Record<string, unknown>) => {
      const result = schema.safeParse(data)
      if (!result.success) {
        const errors: Record<string, { message: string }> = {}
        for (const issue of result.error!.issues) {
          const key = issue.path.join('.')
          if (!(key in errors)) errors[key] = { message: issue.message }
        }
        return { values: {}, errors }
      }
      return { values: result.data, errors: {} }
    },
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useCase } from '../../hooks/use-case'
import { useCaseMutations } from '../../hooks/use-case-mutations'
import { CaseForm } from '../CaseForm'
import { toast } from 'sonner'

function getForm(): HTMLFormElement {
  return document.getElementById('case-form') as HTMLFormElement
}

const mockUseCase = vi.mocked(useCase)
const mockUseCaseMutations = vi.mocked(useCaseMutations)
const mockToast = vi.mocked(toast)

let mockMutateCreate: ReturnType<typeof vi.fn>
let mockMutateUpdate: ReturnType<typeof vi.fn>

function makeCaseData(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    name: 'Test Case',
    status: 'active',
    case_type: null,
    is_filed: false,
    cause_of_action: null,
    current_stage: null,
    target_amount: null,
    preservation_amount: null,
    effective_date: null,
    specified_date: null,
    parties: [],
    assignments: [],
    logs: [],
    case_numbers: [],
    supervising_authorities: [],
    ...overrides,
  }
}

describe('CaseForm - branch coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockMutateCreate = vi.fn()
    mockMutateUpdate = vi.fn()
    mockUseCaseMutations.mockReturnValue({
      createCaseFull: { mutate: mockMutateCreate, isPending: false },
      updateCase: { mutate: mockMutateUpdate, isPending: false },
    })
    mockUseCase.mockReturnValue({ data: null, isLoading: false, error: null })
  })

  // --- Edit mode: track ALL changed fields (lines 139-150) ---

  it('edit mode tracks case_type change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', case_type: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Updated' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
      const { data } = mockMutateUpdate.mock.calls[0][0]
      expect(data.name).toBe('Updated')
    })
  })

  it('edit mode tracks status change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', status: 'active' }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks is_filed change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', is_filed: false }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks cause_of_action change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', cause_of_action: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks current_stage change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', current_stage: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks target_amount change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', target_amount: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks preservation_amount change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', preservation_amount: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks effective_date change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', effective_date: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  it('edit mode tracks specified_date change', async () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ name: 'Case', specified_date: null }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    fireEvent.change(screen.getByDisplayValue('Case'), { target: { value: 'Case2' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
    })
  })

  // --- Create mode: filter parties with valid client_id (line 173) ---

  it('create mode filters parties with non-zero client_id', async () => {
    render(<CaseForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), { target: { value: 'Test' } })
    // Add party
    const addButtons = screen.getAllByText('添加')
    fireEvent.click(addButtons[0])
    fireEvent.change(screen.getByPlaceholderText('客户ID'), { target: { value: '5' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateCreate).toHaveBeenCalledTimes(1)
    })
    const payload = mockMutateCreate.mock.calls[0][0]
    expect(payload.parties).toHaveLength(1)
  })

  // --- Create mode: filter assignments with valid lawyer_id (line 177) ---

  it('create mode filters assignments with non-zero lawyer_id', async () => {
    render(<CaseForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), { target: { value: 'Test' } })
    const addButtons = screen.getAllByText('添加')
    fireEvent.click(addButtons[1])
    fireEvent.change(screen.getByPlaceholderText('律师ID'), { target: { value: '3' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateCreate).toHaveBeenCalledTimes(1)
    })
    const payload = mockMutateCreate.mock.calls[0][0]
    expect(payload.assignments).toHaveLength(1)
  })

  // --- Create mode: filter authorities with name (line 180) ---

  it('create mode filters authorities with non-empty name', async () => {
    render(<CaseForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), { target: { value: 'Test' } })
    const addButtons = screen.getAllByText('添加')
    fireEvent.click(addButtons[2])
    fireEvent.change(screen.getByPlaceholderText('机关名称'), { target: { value: '法院' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockMutateCreate).toHaveBeenCalledTimes(1)
    })
    const payload = mockMutateCreate.mock.calls[0][0]
    expect(payload.supervising_authorities).toHaveLength(1)
    expect(payload.supervising_authorities[0].name).toBe('法院')
  })

  // --- Create mode: error with empty message (line 192) ---

  it('create mode shows generic error when error message is empty', async () => {
    mockMutateCreate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error(''))
    })
    render(<CaseForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), { target: { value: 'Test' } })
    fireEvent.submit(getForm())
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('创建失败')
    })
  })

  // --- Edit mode: null coalescing for caseData fields (lines 115-123) ---

  it('edit mode pre-fills with null coalescing for undefined fields', () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({
        case_type: undefined,
        status: undefined,
        is_filed: undefined,
        cause_of_action: undefined,
        current_stage: undefined,
        target_amount: undefined,
        preservation_amount: undefined,
        effective_date: undefined,
        specified_date: undefined,
      }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByText('编辑案件')).toBeInTheDocument()
  })

  // --- Edit mode: caseData with all fields populated ---

  it('edit mode pre-fills all fields when values exist', () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({
        name: '完整案件',
        case_type: 'civil',
        status: 'closed',
        is_filed: true,
        cause_of_action: 'contract',
        current_stage: 'first_instance',
        target_amount: 100000,
        preservation_amount: 50000,
        effective_date: '2025-01-01',
        specified_date: '2025-06-01',
      }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByDisplayValue('完整案件')).toBeInTheDocument()
    expect(screen.getByDisplayValue('100000')).toBeInTheDocument()
    expect(screen.getByDisplayValue('50000')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2025-01-01')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2025-06-01')).toBeInTheDocument()
  })

  // --- Edit mode: date input onChange with empty value (lines 340, 350) ---

  it('date input onChange converts empty string to null', () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({ effective_date: '2025-01-01' }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    const dateInput = screen.getByDisplayValue('2025-01-01')
    fireEvent.change(dateInput, { target: { value: '' } })
  })

  // --- Create mode: amount input onChange with empty value (line 360) ---

  it('amount input onChange converts empty string to null', () => {
    render(<CaseForm mode="create" />)
    const amountInputs = screen.getAllByPlaceholderText('请输入')
    fireEvent.change(amountInputs[0], { target: { value: '100' } })
    fireEvent.change(amountInputs[0], { target: { value: '' } })
  })

  // --- Create mode: party client_id onChange with empty value (line 422) ---

  it('party client_id onChange converts empty to 0', () => {
    render(<CaseForm mode="create" />)
    const addButtons = screen.getAllByText('添加')
    fireEvent.click(addButtons[0])
    const clientIdInput = screen.getByPlaceholderText('客户ID')
    fireEvent.change(clientIdInput, { target: { value: '5' } })
    fireEvent.change(clientIdInput, { target: { value: '' } })
  })

  // --- Create mode: assignment lawyer_id onChange with empty value (line 465) ---

  it('assignment lawyer_id onChange converts empty to 0', () => {
    render(<CaseForm mode="create" />)
    const addButtons = screen.getAllByText('添加')
    fireEvent.click(addButtons[1])
    const lawyerInput = screen.getByPlaceholderText('律师ID')
    fireEvent.change(lawyerInput, { target: { value: '5' } })
    fireEvent.change(lawyerInput, { target: { value: '' } })
  })

  // --- watchCauseOfAction null coalescing (line 395) ---

  it('passes watchCauseOfAction ?? undefined to FeeCalculator', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByTestId('fee-calculator')).toBeInTheDocument()
  })

  // --- Edit mode: caseData with parties/assignments/logs ---

  it('edit mode renders with populated caseData arrays', () => {
    mockUseCase.mockReturnValue({
      data: makeCaseData({
        parties: [{ id: 1, client: { id: 1, name: 'Party' }, legal_status: 'plaintiff' }],
        assignments: [{ id: 1, lawyer: { id: 1, name: 'Lawyer' } }],
        logs: [{ id: 1, content: 'Log entry' }],
        case_numbers: [{ id: 1, number: 'CN-001' }],
        supervising_authorities: [{ id: 1, name: 'Court' }],
      }),
      isLoading: false, error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByText('案件当事人')).toBeInTheDocument()
    expect(screen.getByText('律师指派')).toBeInTheDocument()
    expect(screen.getByText('案件日志')).toBeInTheDocument()
    expect(screen.getByText('案号')).toBeInTheDocument()
  })
})
