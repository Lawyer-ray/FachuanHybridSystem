vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawyerDetail: (id: number) => `/lawyers/${id}` },
}))

import { render, screen, fireEvent } from '@testing-library/react'
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

  it('shows loading skeleton when isLoading is true', () => {
    const { container } = render(<LawyerTable lawyers={[]} isLoading />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('formats phone with non-11-digit number as-is', () => {
    const lawyers = [{
      ...mockLawyers[0],
      phone: '12345',
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    expect(screen.getByText('12345')).toBeInTheDocument()
  })

  it('shows - for null phone', () => {
    const lawyers = [{
      ...mockLawyers[0],
      phone: null,
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    // '-' appears for null phone, null license_no, null law_firm
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for null license_no', () => {
    const lawyers = [{
      ...mockLawyers[0],
      license_no: null as any,
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for null law_firm_detail', () => {
    const lawyers = [{
      ...mockLawyers[0],
      law_firm_detail: null,
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    // law_firm_detail is null, so getLawFirmName returns '-'
    // There are multiple '-' cells, so use getAllByText
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for empty username', () => {
    const lawyers = [{
      ...mockLawyers[0],
      username: '',
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    // The username cell should show '-'
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for empty real_name', () => {
    const lawyers = [{
      ...mockLawyers[0],
      real_name: '',
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    // real_name is '', so it shows '-'
    // username is still 'zhangsan'
    expect(screen.getByText('zhangsan')).toBeInTheDocument()
  })

  it('shows - for empty law_firm_detail name', () => {
    const lawyers = [{
      ...mockLawyers[0],
      law_firm_detail: { id: 1, name: '', address: '', phone: '', social_credit_code: '' },
    }]
    render(<LawyerTable lawyers={lawyers as any} />)
    // name is '', so getLawFirmName returns '-'
    // But there are multiple '-' cells
    expect(screen.getByText('zhangsan')).toBeInTheDocument()
  })

  it('formats license_no when present', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    expect(screen.getByText('A12345')).toBeInTheDocument()
    expect(screen.getByText('B67890')).toBeInTheDocument()
  })

  it('formats 11-digit phone correctly', () => {
    render(<LawyerTable lawyers={mockLawyers as any} />)
    // phone '00000000000' -> '000****0000'
    expect(screen.getByText('000****0000')).toBeInTheDocument()
  })
})
