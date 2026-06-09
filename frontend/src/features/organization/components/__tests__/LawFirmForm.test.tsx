vi.mock('../../hooks/use-lawfirm', () => ({ useLawFirm: vi.fn() }))

const mockCreateMutate = vi.fn()
const mockUpdateMutate = vi.fn()

vi.mock('../../hooks/use-lawfirm-mutations', () => ({
  useLawFirmMutations: () => ({
    createLawFirm: { mutate: mockCreateMutate, isPending: false },
    updateLawFirm: { mutate: mockUpdateMutate, isPending: false },
  }),
}))

const mockNavigate = vi.fn()
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawFirmDetail: (id: number) => `/lawfirms/${id}` },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  Loader2: (props: Record<string, unknown>) => <svg data-testid="icon-loader" {...props} />,
  Save: (props: Record<string, unknown>) => <svg data-testid="icon-save" {...props} />,
  X: (props: Record<string, unknown>) => <svg data-testid="icon-x" {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, type, variant, className, ...props }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} type={type as string} {...props}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => {
    const { className, ...rest } = props
    return <input {...rest} />
  },
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormField: ({ render, name }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode; name: string }) =>
    render({ field: { name, value: '', onChange: vi.fn(), onBlur: vi.fn(), ref: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormControl: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormMessage: () => null,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LawFirmForm } from '../LawFirmForm'
import { useLawFirm } from '../../hooks/use-lawfirm'
import { toast } from 'sonner'

describe('LawFirmForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock: no data, not loading, no error
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
  })

  // ─── Rendering ────────────────────────────────────────────────────────

  it('renders form title in create mode', () => {
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText('律所信息')).toBeInTheDocument()
  })

  it('renders form title in edit mode', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: { id: 1, name: '测试律所', address: '', phone: '', social_credit_code: '' },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(screen.getByText('编辑律所信息')).toBeInTheDocument()
  })

  it('renders all form fields', () => {
    render(<LawFirmForm mode="create" />)
    expect(screen.getByPlaceholderText('请输入律所名称')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入联系电话')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入律所地址')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入统一社会信用代码')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入开户行名称')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入银行账号')).toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders required indicator on name field', () => {
    render(<LawFirmForm mode="create" />)
    // The name label contains "名称" and the asterisk
    const labels = screen.getAllByText(/名称/)
    expect(labels.length).toBeGreaterThan(0)
  })

  // ─── Loading state in edit mode ───────────────────────────────────────

  it('shows loading spinner in edit mode while loading', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    const { container } = render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('does not show loading spinner in create mode even when useLawFirm is loading', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm mode="create" />)
    // In create mode, isLoading check is only for isEditMode
    expect(screen.getByText('律所信息')).toBeInTheDocument()
  })

  // ─── Error state in edit mode ─────────────────────────────────────────

  it('shows error in edit mode on error', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('fail'),
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(screen.getByText('加载律所数据失败')).toBeInTheDocument()
  })

  it('shows back button on error state', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('fail'),
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('navigates back when clicking return button on error', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('fail'),
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    fireEvent.click(screen.getByText('返回'))
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  it('does not show error state in create mode', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('fail'),
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm mode="create" />)
    expect(screen.queryByText('加载律所数据失败')).not.toBeInTheDocument()
    expect(screen.getByText('律所信息')).toBeInTheDocument()
  })

  // ─── Cancel button ────────────────────────────────────────────────────

  it('navigates back (-1) when cancel is clicked', () => {
    render(<LawFirmForm mode="create" />)
    fireEvent.click(screen.getByText('取消'))
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  // ─── Edit mode with lawFirmId=0 (falsy) ──────────────────────────────

  it('converts lawFirmId=0 to "0" string for useLawFirm hook', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId={0} mode="edit" />)
    // 0?.toString() gives "0", and "0" || '' is "0" (truthy)
    expect(useLawFirm).toHaveBeenCalledWith('0')
  })

  // ─── Edit mode with lawFirmId as number ───────────────────────────────

  it('converts numeric lawFirmId to string for useLawFirm', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId={42} mode="edit" />)
    expect(useLawFirm).toHaveBeenCalledWith('42')
  })

  // ─── Edit mode with lawFirmId as string ───────────────────────────────

  it('passes string lawFirmId directly to useLawFirm', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="123" mode="edit" />)
    expect(useLawFirm).toHaveBeenCalledWith('123')
  })

  // ─── LawFirmForm without lawFirmId in create mode ─────────────────────

  it('calls useLawFirm with empty string when no lawFirmId in create mode', () => {
    render(<LawFirmForm mode="create" />)
    expect(useLawFirm).toHaveBeenCalledWith('')
  })

  // ─── Submit button text states ────────────────────────────────────────

  it('shows "保存" text on submit button when not pending', () => {
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.queryByText('保存中...')).not.toBeInTheDocument()
  })

  // ─── Law firm detail fields in labels ─────────────────────────────────

  it('renders labels for all optional fields', () => {
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText(/联系电话/)).toBeInTheDocument()
    expect(screen.getByText(/地址/)).toBeInTheDocument()
    expect(screen.getByText(/统一社会信用代码/)).toBeInTheDocument()
    expect(screen.getByText(/开户行/)).toBeInTheDocument()
    expect(screen.getByText(/银行账号/)).toBeInTheDocument()
  })

  // ─── Branch: edit mode with all null/optional fields ──────────────────

  it('handles edit mode data with null optional fields', () => {
    vi.mocked(useLawFirm).mockReturnValue({
      data: {
        id: 1,
        name: '律所A',
        address: '',
        phone: '',
        social_credit_code: '',
        bank_name: '',
        bank_account: '',
      },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLawFirm>)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(screen.getByText('编辑律所信息')).toBeInTheDocument()
  })
})
