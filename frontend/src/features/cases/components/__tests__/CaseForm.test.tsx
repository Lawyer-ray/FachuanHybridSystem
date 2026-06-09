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

describe('CaseForm', () => {
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

  // =========================================================================
  // Rendering - Create mode
  // =========================================================================

  describe('Create mode rendering', () => {
    it('renders "新建案件" header', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('新建案件')).toBeInTheDocument()
    })

    it('renders save button with icon', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('保存')).toBeInTheDocument()
    })

    it('renders cancel button', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('取消')).toBeInTheDocument()
    })

    it('renders all form fields', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('案件信息')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('请输入案件名称')).toBeInTheDocument()
      expect(screen.getByText('案件类型')).toBeInTheDocument()
      expect(screen.getByText('状态')).toBeInTheDocument()
      expect(screen.getByText('案由')).toBeInTheDocument()
      expect(screen.getByText('当前阶段')).toBeInTheDocument()
      expect(screen.getByText('生效日期')).toBeInTheDocument()
      expect(screen.getByText('指定日期')).toBeInTheDocument()
      expect(screen.getByText('标的金额')).toBeInTheDocument()
      expect(screen.getByText('保全金额')).toBeInTheDocument()
      expect(screen.getByText('已建档')).toBeInTheDocument()
    })

    it('renders embedded fee calculator', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByTestId('fee-calculator')).toBeInTheDocument()
    })

    it('renders create-only sections (parties, assignments, authorities)', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('当事人')).toBeInTheDocument()
      expect(screen.getByText('指派律师')).toBeInTheDocument()
      expect(screen.getByText('主管机关')).toBeInTheDocument()
    })

    it('shows empty messages for dynamic lists', () => {
      render(<CaseForm mode="create" />)
      expect(screen.getByText('暂无当事人')).toBeInTheDocument()
      expect(screen.getByText('暂未指派律师')).toBeInTheDocument()
      expect(screen.getByText('暂无主管机关')).toBeInTheDocument()
    })

    it('renders three "添加" buttons for dynamic lists', () => {
      render(<CaseForm mode="create" />)
      const addButtons = screen.getAllByText('添加')
      expect(addButtons).toHaveLength(3)
    })

    it('does NOT render edit-only sections', () => {
      render(<CaseForm mode="create" />)
      expect(screen.queryByTestId('party-section')).not.toBeInTheDocument()
      expect(screen.queryByTestId('assignment-section')).not.toBeInTheDocument()
      expect(screen.queryByTestId('log-section')).not.toBeInTheDocument()
      expect(screen.queryByTestId('number-section')).not.toBeInTheDocument()
      expect(screen.queryByTestId('authority-section')).not.toBeInTheDocument()
    })
  })

  // =========================================================================
  // Rendering - Edit mode
  // =========================================================================

  describe('Edit mode rendering', () => {
    it('renders loading spinner while fetching case data', () => {
      mockUseCase.mockReturnValue({ data: null, isLoading: true, error: null })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    })

    it('renders error state with back button on fetch failure', () => {
      mockUseCase.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('not found'),
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByText('加载案件数据失败')).toBeInTheDocument()
      expect(screen.getByText('返回')).toBeInTheDocument()
    })

    it('navigates back when error state "返回" button is clicked', () => {
      mockUseCase.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('fail'),
      })
      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.click(screen.getByText('返回'))
      expect(mockNavigate).toHaveBeenCalledWith(-1)
    })

    it('renders "编辑案件" header when data is loaded', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData(),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByText('编辑案件')).toBeInTheDocument()
    })

    it('renders edit-only sections when data is loaded', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData(),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByText('案件当事人')).toBeInTheDocument()
      expect(screen.getByText('律师指派')).toBeInTheDocument()
      expect(screen.getByText('案件日志')).toBeInTheDocument()
      expect(screen.getByText('案号')).toBeInTheDocument()
      expect(screen.getByTestId('party-section')).toBeInTheDocument()
      expect(screen.getByTestId('assignment-section')).toBeInTheDocument()
      expect(screen.getByTestId('log-section')).toBeInTheDocument()
      expect(screen.getByTestId('number-section')).toBeInTheDocument()
      expect(screen.getByTestId('authority-section')).toBeInTheDocument()
    })

    it('does NOT render create-only sections in edit mode', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData(),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.queryByText('暂无当事人')).not.toBeInTheDocument()
      expect(screen.queryByText('暂未指派律师')).not.toBeInTheDocument()
      expect(screen.queryByText('暂无主管机关')).not.toBeInTheDocument()
    })

    it('pre-fills form with case data in edit mode', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({
          name: 'Pre-filled Case',
          case_type: 'civil',
          status: 'closed',
          is_filed: true,
        }),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByDisplayValue('Pre-filled Case')).toBeInTheDocument()
    })

    it('handles null optional fields when pre-filling', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({
          case_type: null,
          cause_of_action: null,
          current_stage: null,
          target_amount: null,
          preservation_amount: null,
          effective_date: null,
          specified_date: null,
        }),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByText('编辑案件')).toBeInTheDocument()
    })

    it('pre-fills amount and date fields when values exist', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({
          target_amount: 100000,
          preservation_amount: 50000,
          effective_date: '2025-01-01',
          specified_date: '2025-06-01',
        }),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      expect(screen.getByDisplayValue('100000')).toBeInTheDocument()
      expect(screen.getByDisplayValue('50000')).toBeInTheDocument()
      expect(screen.getByDisplayValue('2025-01-01')).toBeInTheDocument()
      expect(screen.getByDisplayValue('2025-06-01')).toBeInTheDocument()
    })
  })

  // =========================================================================
  // Form submission - Create mode
  // =========================================================================

  describe('Create mode submission', () => {
    it('submits valid data via createCaseFull.mutate', async () => {
      render(<CaseForm mode="create" />)

      const nameInput = screen.getByPlaceholderText('请输入案件名称')
      fireEvent.change(nameInput, { target: { value: 'New Case Name' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateCreate).toHaveBeenCalledTimes(1)
      })

      const payload = mockMutateCreate.mock.calls[0][0]
      expect(payload.case.name).toBe('New Case Name')
      expect(payload.case.status).toBe('active')
      expect(payload.parties).toEqual([])
      expect(payload.assignments).toEqual([])
      expect(payload.supervising_authorities).toEqual([])
    })

    it('navigates to case detail on successful create', async () => {
      mockMutateCreate.mockImplementation((_data: unknown, opts: { onSuccess: (res: { case: { id: number } }) => void }) => {
        opts.onSuccess({ case: { id: 42 } })
      })

      render(<CaseForm mode="create" />)
      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.success).toHaveBeenCalledWith('创建成功')
        expect(mockNavigate).toHaveBeenCalledWith('/admin/cases/42')
      })
    })

    it('shows toast error on create failure', async () => {
      mockMutateCreate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
        opts.onError(new Error('Network error'))
      })

      render(<CaseForm mode="create" />)
      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('Network error')
      })
    })

    it('shows generic error toast when error has no message', async () => {
      mockMutateCreate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
        opts.onError(new Error(''))
      })

      render(<CaseForm mode="create" />)
      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('创建失败')
      })
    })

    it('filters out empty parties from payload', async () => {
      render(<CaseForm mode="create" />)

      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })

      // Add two parties and fill both with valid data
      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[0])
      fireEvent.click(addButtons[0])

      const clientIdInputs = screen.getAllByPlaceholderText('客户ID')
      fireEvent.change(clientIdInputs[0], { target: { value: '10' } })
      fireEvent.change(clientIdInputs[1], { target: { value: '100' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateCreate).toHaveBeenCalledTimes(1)
      })

      const payload = mockMutateCreate.mock.calls[0][0]
      expect(payload.parties).toHaveLength(2)
      expect(payload.parties[0].client_id).toBe(10)
      expect(payload.parties[1].client_id).toBe(100)
    })

    it('filters out empty assignments from payload', async () => {
      render(<CaseForm mode="create" />)

      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })

      // Add an assignment with a lawyer_id
      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[1])

      const lawyerInput = screen.getByPlaceholderText('律师ID')
      fireEvent.change(lawyerInput, { target: { value: '50' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        const payload = mockMutateCreate.mock.calls[0][0]
        expect(payload.assignments).toHaveLength(1)
        expect(payload.assignments[0].lawyer_id).toBe(50)
      })
    })

    it('filters out empty authorities from payload', async () => {
      render(<CaseForm mode="create" />)

      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Test' },
      })

      // Add an authority with a name
      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[2])

      const authNameInput = screen.getByPlaceholderText('机关名称')
      fireEvent.change(authNameInput, { target: { value: '某法院' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        const payload = mockMutateCreate.mock.calls[0][0]
        expect(payload.supervising_authorities).toHaveLength(1)
        expect(payload.supervising_authorities[0].name).toBe('某法院')
      })
    })

    it('builds payload with all fields populated', async () => {
      render(<CaseForm mode="create" />)

      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Full Case' },
      })

      const amountInputs = screen.getAllByPlaceholderText('请输入')
      fireEvent.change(amountInputs[0], { target: { value: '50000' } })
      fireEvent.change(amountInputs[1], { target: { value: '10000' } })

      const dateInputs = screen.getAllByDisplayValue('')
      // Set date fields
      const effectiveDateInput = screen.getByText('生效日期').closest('div')?.querySelector('input[type="date"]')
      const specifiedDateInput = screen.getByText('指定日期').closest('div')?.querySelector('input[type="date"]')
      if (effectiveDateInput) fireEvent.change(effectiveDateInput, { target: { value: '2025-01-15' } })
      if (specifiedDateInput) fireEvent.change(specifiedDateInput, { target: { value: '2025-07-01' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateCreate).toHaveBeenCalledTimes(1)
      })

      const payload = mockMutateCreate.mock.calls[0][0]
      expect(payload.case.name).toBe('Full Case')
      expect(payload.case.target_amount).toBe(50000)
      expect(payload.case.preservation_amount).toBe(10000)
      expect(payload.case.effective_date).toBe('2025-01-15')
      expect(payload.case.specified_date).toBe('2025-07-01')
    })
  })

  // =========================================================================
  // Form submission - Edit mode
  // =========================================================================

  describe('Edit mode submission', () => {
    it('submits only changed fields via updateCase.mutate', async () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({ name: 'Original Name', status: 'active' }),
        isLoading: false,
        error: null,
      })

      render(<CaseForm caseId="1" mode="edit" />)

      // Change name from 'Original Name' to 'Updated Name'
      const nameInput = screen.getByDisplayValue('Original Name')
      fireEvent.change(nameInput, { target: { value: 'Updated Name' } })

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
      })

      const { id, data } = mockMutateUpdate.mock.calls[0][0]
      expect(id).toBe('1')
      expect(data.name).toBe('Updated Name')
      expect(data.status).toBeUndefined()
    })

    it('navigates to case detail on successful update', async () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({ name: 'Case' }),
        isLoading: false,
        error: null,
      })
      mockMutateUpdate.mockImplementation((_params: unknown, opts: { onSuccess: () => void }) => {
        opts.onSuccess()
      })

      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.change(screen.getByDisplayValue('Case'), {
        target: { value: 'Updated' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.success).toHaveBeenCalledWith('保存成功')
        expect(mockNavigate).toHaveBeenCalledWith('/admin/cases/1')
      })
    })

    it('shows toast error on update failure', async () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({ name: 'Case' }),
        isLoading: false,
        error: null,
      })
      mockMutateUpdate.mockImplementation((_params: unknown, opts: { onError: (err: Error) => void }) => {
        opts.onError(new Error('Update failed'))
      })

      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.change(screen.getByDisplayValue('Case'), {
        target: { value: 'Updated' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('Update failed')
      })
    })

    it('shows generic error toast when update error has no message', async () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({ name: 'Case' }),
        isLoading: false,
        error: null,
      })
      mockMutateUpdate.mockImplementation((_params: unknown, opts: { onError: (err: Error) => void }) => {
        opts.onError(new Error(''))
      })

      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.change(screen.getByDisplayValue('Case'), {
        target: { value: 'Updated' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('保存失败')
      })
    })

    it('tracks unchanged fields are excluded from update', async () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData({ name: 'Case', status: 'active' }),
        isLoading: false,
        error: null,
      })

      render(<CaseForm caseId="1" mode="edit" />)

      // Change only the name field
      fireEvent.change(screen.getByDisplayValue('Case'), {
        target: { value: 'Updated Case' },
      })

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateUpdate).toHaveBeenCalledTimes(1)
      })

      const { data } = mockMutateUpdate.mock.calls[0][0]
      expect(data.name).toBe('Updated Case')
      // Unchanged fields should not be in the update
      expect(data.status).toBeUndefined()
      expect(data.case_type).toBeUndefined()
      expect(data.is_filed).toBeUndefined()
      expect(data.target_amount).toBeUndefined()
      expect(data.preservation_amount).toBeUndefined()
      expect(data.effective_date).toBeUndefined()
      expect(data.specified_date).toBeUndefined()
    })
  })

  // =========================================================================
  // Validation
  // =========================================================================

  describe('Validation', () => {
    it('shows validation error when name is empty', async () => {
      render(<CaseForm mode="create" />)

      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(screen.getByText('案件名称不能为空')).toBeInTheDocument()
      })
      expect(mockMutateCreate).not.toHaveBeenCalled()
    })

    it('clears validation error when field is corrected', async () => {
      render(<CaseForm mode="create" />)

      // Submit empty to trigger error
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(screen.getByText('案件名称不能为空')).toBeInTheDocument()
      })

      // Fix the field and resubmit
      fireEvent.change(screen.getByPlaceholderText('请输入案件名称'), {
        target: { value: 'Fixed Name' },
      })
      fireEvent.submit(getForm())

      await waitFor(() => {
        expect(mockMutateCreate).toHaveBeenCalled()
      })
      expect(screen.queryByText('案件名称不能为空')).not.toBeInTheDocument()
    })
  })

  // =========================================================================
  // Pending / loading state
  // =========================================================================

  describe('Pending state', () => {
    it('shows "保存中..." and disables buttons during create submission', () => {
      mockUseCaseMutations.mockReturnValue({
        createCaseFull: { mutate: vi.fn(), isPending: true },
        updateCase: { mutate: vi.fn(), isPending: false },
      })

      render(<CaseForm mode="create" />)

      expect(screen.getByText('保存中...')).toBeInTheDocument()
      expect(screen.queryByText('保存')).not.toBeInTheDocument()

      const cancelButton = screen.getByText('取消')
      const submitButton = screen.getByText('保存中...').closest('button')
      expect(cancelButton).toBeDisabled()
      expect(submitButton).toBeDisabled()
    })

    it('disables name input during pending state', () => {
      mockUseCaseMutations.mockReturnValue({
        createCaseFull: { mutate: vi.fn(), isPending: true },
        updateCase: { mutate: vi.fn(), isPending: false },
      })

      render(<CaseForm mode="create" />)

      const nameInput = screen.getByPlaceholderText('请输入案件名称')
      expect(nameInput).toBeDisabled()
    })

    it('disables amount inputs during pending state', () => {
      mockUseCaseMutations.mockReturnValue({
        createCaseFull: { mutate: vi.fn(), isPending: true },
        updateCase: { mutate: vi.fn(), isPending: false },
      })

      render(<CaseForm mode="create" />)

      const amountInputs = screen.getAllByPlaceholderText('请输入')
      amountInputs.forEach((input) => expect(input).toBeDisabled())
    })
  })

  // =========================================================================
  // Navigation
  // =========================================================================

  describe('Navigation', () => {
    it('navigates to ADMIN_CASES when back link is clicked in create mode', () => {
      render(<CaseForm mode="create" />)
      fireEvent.click(screen.getByText('新建案件'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases')
    })

    it('navigates to case detail when back link is clicked in edit mode', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData(),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.click(screen.getByText('编辑案件'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases/1')
    })

    it('navigates to ADMIN_CASES when cancel is clicked in create mode', () => {
      render(<CaseForm mode="create" />)
      fireEvent.click(screen.getByText('取消'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases')
    })

    it('navigates to case detail when cancel is clicked in edit mode', () => {
      mockUseCase.mockReturnValue({
        data: makeCaseData(),
        isLoading: false,
        error: null,
      })
      render(<CaseForm caseId="1" mode="edit" />)
      fireEvent.click(screen.getByText('取消'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases/1')
    })
  })

  // =========================================================================
  // Dynamic lists (create mode)
  // =========================================================================

  describe('Dynamic lists in create mode', () => {
    it('adds and removes parties', () => {
      render(<CaseForm mode="create" />)

      expect(screen.getByText('暂无当事人')).toBeInTheDocument()

      // Add a party
      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[0])

      expect(screen.queryByText('暂无当事人')).not.toBeInTheDocument()
      expect(screen.getByPlaceholderText('客户ID')).toBeInTheDocument()

      // Remove the party
      const trashButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('.text-muted-foreground.size-3')
      )
      fireEvent.click(trashButtons[0])

      expect(screen.getByText('暂无当事人')).toBeInTheDocument()
    })

    it('adds and removes assignments', () => {
      render(<CaseForm mode="create" />)

      expect(screen.getByText('暂未指派律师')).toBeInTheDocument()

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[1])

      expect(screen.queryByText('暂未指派律师')).not.toBeInTheDocument()
      expect(screen.getByPlaceholderText('律师ID')).toBeInTheDocument()

      // Remove the assignment
      const trashButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('.text-muted-foreground.size-3')
      )
      fireEvent.click(trashButtons[0])

      expect(screen.getByText('暂未指派律师')).toBeInTheDocument()
    })

    it('adds and removes authorities', () => {
      render(<CaseForm mode="create" />)

      expect(screen.getByText('暂无主管机关')).toBeInTheDocument()

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[2])

      expect(screen.queryByText('暂无主管机关')).not.toBeInTheDocument()
      expect(screen.getByPlaceholderText('机关名称')).toBeInTheDocument()

      // Remove the authority
      const trashButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('.text-muted-foreground.size-3')
      )
      fireEvent.click(trashButtons[0])

      expect(screen.getByText('暂无主管机关')).toBeInTheDocument()
    })

    it('adds multiple parties', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[0])
      fireEvent.click(addButtons[0])

      const clientIdInputs = screen.getAllByPlaceholderText('客户ID')
      expect(clientIdInputs).toHaveLength(2)
    })

    it('removes specific party by index', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')

      // Add two parties
      fireEvent.click(addButtons[0])
      fireEvent.click(addButtons[0])

      const clientIdInputs = screen.getAllByPlaceholderText('客户ID')
      expect(clientIdInputs).toHaveLength(2)

      // Set values
      fireEvent.change(clientIdInputs[0], { target: { value: '1' } })
      fireEvent.change(clientIdInputs[1], { target: { value: '2' } })

      // Remove first party
      const trashButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('.text-muted-foreground.size-3')
      )
      fireEvent.click(trashButtons[0])

      const remainingInputs = screen.getAllByPlaceholderText('客户ID')
      expect(remainingInputs).toHaveLength(1)
    })

    it('adds multiple authorities', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[2])
      fireEvent.click(addButtons[2])

      const authInputs = screen.getAllByPlaceholderText('机关名称')
      expect(authInputs).toHaveLength(2)
    })
  })

  // =========================================================================
  // Interactive elements
  // =========================================================================

  describe('Interactive elements', () => {
    it('updates name input value', () => {
      render(<CaseForm mode="create" />)
      const input = screen.getByPlaceholderText('请输入案件名称')
      fireEvent.change(input, { target: { value: 'My Case' } })
      expect(input).toHaveValue('My Case')
    })

    it('handles number input for target amount', () => {
      render(<CaseForm mode="create" />)
      const amountInputs = screen.getAllByPlaceholderText('请输入')
      fireEvent.change(amountInputs[0], { target: { value: '12345' } })
      expect(amountInputs[0]).toHaveValue(12345)
    })

    it('handles empty value for target amount (converts to null)', () => {
      render(<CaseForm mode="create" />)
      const amountInputs = screen.getAllByPlaceholderText('请输入')
      fireEvent.change(amountInputs[0], { target: { value: '100' } })
      fireEvent.change(amountInputs[0], { target: { value: '' } })
      // Empty string should resolve to null internally
    })

    it('handles date input changes', () => {
      render(<CaseForm mode="create" />)
      const effectiveDateInput = screen.getByText('生效日期').closest('div')?.querySelector('input[type="date"]') as HTMLInputElement
      fireEvent.change(effectiveDateInput, { target: { value: '2025-03-15' } })
      expect(effectiveDateInput.value).toBe('2025-03-15')
    })

    it('handles date input clearing (converts to null)', () => {
      render(<CaseForm mode="create" />)
      const effectiveDateInput = screen.getByText('生效日期').closest('div')?.querySelector('input[type="date"]') as HTMLInputElement
      fireEvent.change(effectiveDateInput, { target: { value: '2025-03-15' } })
      fireEvent.change(effectiveDateInput, { target: { value: '' } })
      expect(effectiveDateInput.value).toBe('')
    })

    it('handles party client_id input as number', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[0])

      const clientIdInput = screen.getByPlaceholderText('客户ID')
      fireEvent.change(clientIdInput, { target: { value: '42' } })
      expect(clientIdInput).toHaveValue(42)
    })

    it('handles party client_id empty input (converts to 0)', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[0])

      const clientIdInput = screen.getByPlaceholderText('客户ID')
      fireEvent.change(clientIdInput, { target: { value: '10' } })
      fireEvent.change(clientIdInput, { target: { value: '' } })
      // Empty string -> 0 via the onChange handler
    })

    it('handles assignment lawyer_id input as number', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[1])

      const lawyerInput = screen.getByPlaceholderText('律师ID')
      fireEvent.change(lawyerInput, { target: { value: '7' } })
      expect(lawyerInput).toHaveValue(7)
    })

    it('handles authority name input', () => {
      render(<CaseForm mode="create" />)

      const addButtons = screen.getAllByText('添加')
      fireEvent.click(addButtons[2])

      const nameInput = screen.getByPlaceholderText('机关名称')
      fireEvent.change(nameInput, { target: { value: '公安局' } })
      expect(nameInput).toHaveValue('公安局')
    })
  })

  // =========================================================================
  // Default export
  // =========================================================================

  it('exports CaseForm as default export', async () => {
    const mod = await import('../CaseForm')
    expect(mod.default).toBe(mod.CaseForm)
  })
})
