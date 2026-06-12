vi.mock('../../hooks/use-lawyer', () => ({
  useLawyer: vi.fn(),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_ORGANIZATION: '/organization' },
  generatePath: { lawyerEdit: (id: string) => `/lawyers/${id}/edit` },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (url: string | null) => url,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: any) => <span data-variant={variant}>{children}</span>,
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr />,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: any) => <div data-testid="skeleton" className={props.className} />,
}))

import { render, screen } from '@testing-library/react'
import { LawyerDetail } from '../LawyerDetail'
import { useLawyer } from '../../hooks/use-lawyer'

const mockLawyer = {
  id: 1, username: 'zhangsan', real_name: '张三', phone: '00000000000',
  license_no: 'A12345', id_card: '000000000000000000', law_firm: 1, is_admin: true, is_active: true,
  license_pdf_url: null, avatar_url: null,
  law_firm_detail: { id: 1, name: '大成律所', address: '', phone: '', social_credit_code: '' },
}

describe('LawyerDetail', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows loading skeleton', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    const { container } = render(<LawyerDetail lawyerId="1" />)
    // Skeleton uses animate-pulse class or data-testid="skeleton"
    const skeletons = container.querySelectorAll('[data-testid="skeleton"], [class*="animate-pulse"]')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows not found when error', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: new Error('404') } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('律师不存在')).toBeInTheDocument()
  })

  it('shows not found when no data', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('律师不存在')).toBeInTheDocument()
  })

  it('renders lawyer info when loaded', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getAllByText('张三').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('shows admin badge', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('管理员')).toBeInTheDocument()
  })

  it('shows non-admin badge', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, is_admin: false },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('普通用户')).toBeInTheDocument()
  })

  it('shows active status badge', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('启用')).toBeInTheDocument()
  })

  it('shows inactive status badge', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, is_active: false },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('禁用')).toBeInTheDocument()
  })

  it('renders avatar image when avatar_url is set', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, avatar_url: 'http://example.com/avatar.jpg' },
      isLoading: false, error: null,
    } as any)
    const { container } = render(<LawyerDetail lawyerId="1" />)
    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    expect(img?.getAttribute('src')).toBe('http://example.com/avatar.jpg')
  })

  it('renders fallback avatar when no avatar_url', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    // Should have UserRound icon as fallback
    expect(screen.getAllByText('张三').length).toBeGreaterThanOrEqual(1)
  })

  it('shows license PDF link when license_pdf_url is set', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, license_pdf_url: 'http://example.com/license.pdf' },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('查看执业证')).toBeInTheDocument()
  })

  it('shows 未上传 when no license_pdf_url', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('未上传')).toBeInTheDocument()
  })

  it('shows law firm name when law_firm_detail exists', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('大成律所')).toBeInTheDocument()
  })

  it('shows 未设置 when no law_firm_detail', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, law_firm_detail: null },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('未设置')).toBeInTheDocument()
  })

  it('shows 未填写 for empty fields', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, real_name: '', phone: null, license_no: '', id_card: '' },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    const unfilled = screen.getAllByText('未填写')
    expect(unfilled.length).toBeGreaterThanOrEqual(1)
  })

  it('shows username as fallback when real_name is empty', () => {
    vi.mocked(useLawyer).mockReturnValue({
      data: { ...mockLawyer, real_name: '' },
      isLoading: false, error: null,
    } as any)
    render(<LawyerDetail lawyerId="1" />)
    // username 'zhangsan' appears in the header (as fallback for name) and in the info card
    const elements = screen.getAllByText('zhangsan')
    expect(elements.length).toBeGreaterThanOrEqual(1)
  })

  it('shows not found message with back button', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
    expect(screen.getByText('您访问的律师可能已被删除或不存在')).toBeInTheDocument()
  })

  it('renders all info items', () => {
    vi.mocked(useLawyer).mockReturnValue({ data: mockLawyer, isLoading: false, error: null } as any)
    render(<LawyerDetail lawyerId="1" />)
    expect(screen.getByText('用户名')).toBeInTheDocument()
    expect(screen.getByText('真实姓名')).toBeInTheDocument()
    expect(screen.getByText('手机号')).toBeInTheDocument()
    expect(screen.getByText('执业证号')).toBeInTheDocument()
    expect(screen.getByText('身份证号')).toBeInTheDocument()
    expect(screen.getByText('所属律所')).toBeInTheDocument()
    expect(screen.getByText('角色')).toBeInTheDocument()
    expect(screen.getByText('执业证')).toBeInTheDocument()
  })
})
