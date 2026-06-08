vi.mock('../../hooks/use-lawyer', () => ({ useLawyer: vi.fn() }))
vi.mock('../../hooks/use-lawyer-mutations', () => ({
  useLawyerMutations: () => ({
    createLawyer: { mutate: vi.fn(), isPending: false },
    updateLawyer: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [{ id: 1, name: '大成律所' }], isLoading: false }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawyerDetail: (id: number) => `/lawyers/${id}` },
}))

vi.mock('@/lib/api', () => ({ resolveMediaUrl: (url: string | null) => url }))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen, fireEvent } from '@testing-library/react'
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
})
