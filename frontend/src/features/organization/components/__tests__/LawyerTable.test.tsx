vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawyerDetail: (id: number) => `/lawyers/${id}` },
}))

import { render, screen } from '@testing-library/react'
import { LawyerTable } from '../LawyerTable'

describe('LawyerTable', () => {
  const mockLawyers = [
    {
      id: 1, username: 'zhangsan', real_name: '张三', phone: '00000000000',
      license_no: 'A12345', id_card: '', law_firm: 1, is_admin: true, is_active: true,
      license_pdf_url: null, avatar_url: null, law_firm_detail: { id: 1, name: '大成律所', address: '', phone: '', social_credit_code: '' },
    },
    {
      id: 2, username: 'lisi', real_name: '李四', phone: '00000000001',
      license_no: 'B67890', id_card: '', law_firm: null, is_admin: false, is_active: false,
      license_pdf_url: null, avatar_url: null, law_firm_detail: null,
    },
  ]

  it('renders table headers', () => {
    render(<LawyerTable lawyers={[]} />)
    expect(screen.getByText('用户名')).toBeInTheDocument()
    expect(screen.getByText('真实姓名')).toBeInTheDocument()
    expect(screen.getByText('手机号')).toBeInTheDocument()
    expect(screen.getByText('执业证号')).toBeInTheDocument()
    expect(screen.getByText('所属律所')).toBeInTheDocument()
    expect(screen.getByText('是否管理员')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
  })

  it('renders lawyer data rows', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    expect(screen.getByText('zhangsan')).toBeInTheDocument()
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('lisi')).toBeInTheDocument()
    expect(screen.getByText('李四')).toBeInTheDocument()
  })

  it('renders empty state when no lawyers', () => {
    render(<LawyerTable lawyers={[]} />)
    expect(screen.getByText('暂无律师数据')).toBeInTheDocument()
  })

  it('shows admin badge for admin users', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    expect(screen.getByText('管理员')).toBeInTheDocument()
    expect(screen.getByText('普通用户')).toBeInTheDocument()
  })

  it('shows active/inactive status badges', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    expect(screen.getByText('启用')).toBeInTheDocument()
    expect(screen.getByText('禁用')).toBeInTheDocument()
  })

  it('renders phone in masked format', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    expect(screen.getByText('000****0001')).toBeInTheDocument()
  })
})
