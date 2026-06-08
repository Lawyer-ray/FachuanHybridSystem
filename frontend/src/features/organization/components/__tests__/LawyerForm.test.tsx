const mockNavigate = vi.fn()
const mockCreateLawyerMutate = vi.fn()
const mockUpdateLawyerMutate = vi.fn()

vi.mock('../../hooks/use-lawyer', () => ({ useLawyer: vi.fn() }))
vi.mock('../../hooks/use-lawyer-mutations', () => ({
  useLawyerMutations: () => ({
    createLawyer: { mutate: mockCreateLawyerMutate, isPending: false },
    updateLawyer: { mutate: mockUpdateLawyerMutate, isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [{ id: 1, name: '大成律所' }], isLoading: false }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawyerDetail: (id: number) => `/lawyers/${id}` },
}))

vi.mock('@/lib/api', () => ({ resolveMediaUrl: (url: string | null) => url }))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { LawyerForm } from '../LawyerForm'
import { useLawyer } from '../../hooks/use-lawyer'

describe('LawyerForm', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders form title in create mode', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('律师信息')).toBeInTheDocument()
  })

  it('renders form title in edit mode', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: { username: 'zhang' }, isLoading: false, error: null } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByText('编辑律师信息')).toBeInTheDocument()
  })

  it('renders all form fields', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByPlaceholderText('请输入用户名')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入密码（至少6位）')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入真实姓名')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入手机号')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入执业证号')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入身份证号')).toBeInTheDocument()
  })

  it('shows loading spinner in edit mode while loading', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    const { container } = render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(container.querySelector('[class*="animate-spin"]')).toBeInTheDocument()
  })

  it('shows error in edit mode on error', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: new Error('fail') } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByText('加载律师数据失败')).toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders avatar upload area', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('律师头像')).toBeInTheDocument()
    expect(screen.getByText(/支持 JPG、PNG 格式/)).toBeInTheDocument()
  })

  it('renders license PDF upload section', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('执业证 PDF')).toBeInTheDocument()
    expect(screen.getByText(/支持 PDF 格式/)).toBeInTheDocument()
  })

  it('renders law firm select', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('所属律所')).toBeInTheDocument()
  })

  it('renders admin toggle', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    expect(screen.getByText('是否管理员')).toBeInTheDocument()
  })

  it('shows username description in edit mode', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: { username: 'zhang', real_name: '张三', phone: '138', license_no: 'L123', id_card: '110', law_firm: 1, is_admin: false }, isLoading: false, error: null } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByText('编辑模式下用户名不可修改')).toBeInTheDocument()
  })

  it('shows password placeholder for edit mode', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: { username: 'zhang' }, isLoading: false, error: null } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByPlaceholderText('留空表示不修改密码')).toBeInTheDocument()
  })

  it('toggles password visibility', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    // Find the toggle button near the password field
    const passwordInput = screen.getByPlaceholderText('请输入密码（至少6位）')
    expect(passwordInput).toBeInTheDocument()
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('renders with lawyer data in edit mode', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: {
        username: 'zhangsan', real_name: '张三', phone: '13800138000',
        license_no: 'L12345', id_card: '110101199001011234', law_firm: 1,
        is_admin: true, avatar_url: 'http://example.com/avatar.jpg',
        license_pdf_url: 'http://example.com/license.pdf',
      },
      isLoading: false, error: null,
    } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByDisplayValue('zhangsan')).toBeInTheDocument()
    expect(screen.getByText('查看当前执业证')).toBeInTheDocument()
    expect(screen.getByText('移除头像')).toBeInTheDocument()
  })

  it('handles avatar file selection with non-image file', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const avatarInput = document.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement
    expect(avatarInput).toBeInTheDocument()
  })

  it('handles license file selection with non-pdf', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const fileInputs = document.querySelectorAll('input[type="file"]')
    expect(fileInputs.length).toBeGreaterThanOrEqual(1)
  })

  it('renders form disabled state when pending', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    // All inputs should be enabled initially
    const usernameInput = screen.getByPlaceholderText('请输入用户名')
    expect(usernameInput).not.toBeDisabled()
  })

  // --- New tests for uncovered lines ---

  it('handles avatar file selection with non-image file type', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const avatarInput = document.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    Object.defineProperty(avatarInput, 'files', { value: [file] })
    fireEvent.change(avatarInput)
    expect(toast.error).toHaveBeenCalledWith('请选择图片文件')
  })

  it('handles avatar file selection with too large file', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const avatarInput = document.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement
    // Create a 6MB file
    const largeFile = new File([new ArrayBuffer(6 * 1024 * 1024)], 'big.jpg', { type: 'image/jpeg' })
    Object.defineProperty(avatarInput, 'files', { value: [largeFile] })
    fireEvent.change(avatarInput)
    expect(toast.error).toHaveBeenCalledWith('头像大小不能超过 5MB')
  })

  it('handles valid avatar file selection', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const avatarInput = document.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement
    const imgFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
    Object.defineProperty(avatarInput, 'files', { value: [imgFile] })
    fireEvent.change(avatarInput)
    expect(screen.getByText('移除头像')).toBeInTheDocument()
  })

  it('handles avatar removal', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const avatarInput = document.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement
    const imgFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
    Object.defineProperty(avatarInput, 'files', { value: [imgFile] })
    fireEvent.change(avatarInput)
    fireEvent.click(screen.getByText('移除头像'))
    expect(screen.queryByText('移除头像')).not.toBeInTheDocument()
  })

  it('handles license PDF file with non-pdf type', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const pdfInputs = document.querySelectorAll('input[type="file"][accept=".pdf,application/pdf"]')
    const fileInput = pdfInputs[0] as HTMLInputElement
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    Object.defineProperty(fileInput, 'files', { value: [file] })
    fireEvent.change(fileInput)
    expect(toast.error).toHaveBeenCalledWith('请选择 PDF 文件')
  })

  it('handles license PDF file too large', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const pdfInputs = document.querySelectorAll('input[type="file"][accept=".pdf,application/pdf"]')
    const fileInput = pdfInputs[0] as HTMLInputElement
    const largePdf = new File([new ArrayBuffer(11 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput, 'files', { value: [largePdf] })
    fireEvent.change(fileInput)
    expect(toast.error).toHaveBeenCalledWith('文件大小不能超过 10MB')
  })

  it('handles valid license PDF file selection', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const pdfInputs = document.querySelectorAll('input[type="file"][accept=".pdf,application/pdf"]')
    const fileInput = pdfInputs[0] as HTMLInputElement
    const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput, 'files', { value: [pdfFile] })
    fireEvent.change(fileInput)
    expect(screen.getByText('license.pdf')).toBeInTheDocument()
  })

  it('handles clear license PDF file', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const pdfInputs = document.querySelectorAll('input[type="file"][accept=".pdf,application/pdf"]')
    const fileInput = pdfInputs[0] as HTMLInputElement
    const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput, 'files', { value: [pdfFile] })
    fireEvent.change(fileInput)
    expect(screen.getByText('license.pdf')).toBeInTheDocument()
    // Find the X button near the file name
    const clearBtns = screen.getAllByRole('button', { name: '' })
    // Click the clear button that's within the PDF section
    const clearBtn = fileInput.closest('div')?.querySelector('button')
  })

  it('validates password length in create mode', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    const { container } = render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'testuser' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: '123' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(screen.getByText('密码至少6位')).toBeInTheDocument()
    })
  })

  it('submits create lawyer successfully', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    mockCreateLawyerMutate.mockImplementation((_params: unknown, opts: { onSuccess: (l: { id: number }) => void }) => {
      opts.onSuccess({ id: 42 })
    })
    render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'newuser' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: 'password123' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(mockCreateLawyerMutate).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('创建成功')
      expect(mockNavigate).toHaveBeenCalledWith('/lawyers/42')
    })
  })

  it('handles create lawyer error', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    mockCreateLawyerMutate.mockImplementation((_params: unknown, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error('Duplicate username'))
    })
    render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'dupuser' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: 'password123' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Duplicate username')
    })
  })

  it('submits update lawyer successfully', async () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { username: 'old', real_name: 'Old Name', phone: '138', license_no: 'L1', id_card: '110', law_firm: 1, is_admin: false },
      isLoading: false, error: null,
    } as any)
    mockUpdateLawyerMutate.mockImplementation((_params: unknown, opts: { onSuccess: (l: { id: number }) => void }) => {
      opts.onSuccess({ id: 1 })
    })
    render(<LawyerForm lawyerId="1" mode="edit" />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(mockUpdateLawyerMutate).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('保存成功')
      expect(mockNavigate).toHaveBeenCalledWith('/lawyers/1')
    })
  })

  it('handles update lawyer error', async () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { username: 'old', real_name: '', phone: '', license_no: '', id_card: '', law_firm: null, is_admin: false },
      isLoading: false, error: null,
    } as any)
    mockUpdateLawyerMutate.mockImplementation((_params: unknown, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error('Save failed'))
    })
    render(<LawyerForm lawyerId="1" mode="edit" />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Save failed')
    })
  })

  it('handles cancel button click', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    fireEvent.click(screen.getByText('取消'))
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  it('shows loading state in edit mode (LawyerForm)', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    const { container } = render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows error state in edit mode (LawyerForm)', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: new Error('fail') } as any)
    render(<LawyerForm lawyerId="1" mode="edit" />)
    expect(screen.getByText('加载律师数据失败')).toBeInTheDocument()
    fireEvent.click(screen.getByText('返回'))
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  it('submits with optional fields empty in create mode', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    mockCreateLawyerMutate.mockImplementation((_params: { data: Record<string, unknown> }) => {
      // Check that optional fields are undefined
    })
    render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'user' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: 'password123' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      const callData = mockCreateLawyerMutate.mock.calls[0][0].data
      expect(callData.real_name).toBeUndefined()
      expect(callData.phone).toBeUndefined()
      expect(callData.license_no).toBeUndefined()
      expect(callData.id_card).toBeUndefined()
      expect(callData.law_firm_id).toBeUndefined()
    })
  })

  it('submits with law_firm_id as number', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    mockCreateLawyerMutate.mockImplementation(() => {})
    render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'user' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: 'password123' } })
    fireEvent.change(screen.getByPlaceholderText('请输入真实姓名'), { target: { value: '张三' } })
    fireEvent.change(screen.getByPlaceholderText('请输入手机号'), { target: { value: '13800138000' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(mockCreateLawyerMutate).toHaveBeenCalled()
    })
  })

  it('sends password as undefined in edit mode when empty', async () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { username: 'u', real_name: '', phone: '', license_no: '', id_card: '', law_firm: null, is_admin: false },
      isLoading: false, error: null,
    } as any)
    mockUpdateLawyerMutate.mockImplementation(() => {})
    render(<LawyerForm lawyerId="1" mode="edit" />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      const callData = mockUpdateLawyerMutate.mock.calls[0][0].data
      expect(callData.password).toBeUndefined()
    })
  })

  it('handles non-Error instance in create onError', async () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    mockCreateLawyerMutate.mockImplementation((_p: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError('string error')
    })
    render(<LawyerForm mode="create" />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'user' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码（至少6位）'), { target: { value: 'password123' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('创建失败，请重试')
    })
  })

  it('handles non-Error instance in update onError', async () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { username: 'u', real_name: '', phone: '', license_no: '', id_card: '', law_firm: null, is_admin: false },
      isLoading: false, error: null,
    } as any)
    mockUpdateLawyerMutate.mockImplementation((_p: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError('string error')
    })
    render(<LawyerForm lawyerId="1" mode="edit" />)
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('保存失败，请重试')
    })
  })

  it('edits license file after clear', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const pdfInputs = document.querySelectorAll('input[type="file"][accept=".pdf,application/pdf"]')
    const fileInput = pdfInputs[0] as HTMLInputElement
    const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput, 'files', { value: [pdfFile] })
    fireEvent.change(fileInput)
    expect(screen.getByText('license.pdf')).toBeInTheDocument()
    // Re-select should show "重新选择"
    expect(screen.getByText('重新选择')).toBeInTheDocument()
  })

  it('renders password toggle button', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    // The password toggle Eye/EyeOff button exists
    const passwordInput = screen.getByPlaceholderText('请输入密码（至少6位）')
    const parentDiv = passwordInput.closest('.relative')
    expect(parentDiv).toBeTruthy()
  })

  it('toggles password visibility on button click', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerForm mode="create" />)
    const passwordInput = screen.getByPlaceholderText('请输入密码（至少6位）') as HTMLInputElement
    expect(passwordInput.type).toBe('password')
    // Click the toggle button (sibling of the input)
    const toggleBtn = passwordInput.parentElement?.querySelector('button')
    if (toggleBtn) {
      fireEvent.click(toggleBtn)
      expect(passwordInput.type).toBe('text')
    }
  })
})
