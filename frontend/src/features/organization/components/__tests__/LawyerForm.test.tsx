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

import { render, screen } from '@testing-library/react'
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
})
