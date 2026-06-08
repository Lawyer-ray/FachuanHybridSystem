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
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
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
})
