vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawFirmDetail: (id: number) => `/lawfirms/${id}` },
}))

import { render, screen } from '@testing-library/react'
import { LawFirmTable } from '../LawFirmTable'

describe('LawFirmTable', () => {
  const mockFirms = [
    { id: 1, name: '大成律所', address: '北京市朝阳区建国路88号SOHO', phone: '01012345678', social_credit_code: '91110000MA0123456789' },
    { id: 2, name: '金杜律所', address: '上海市浦东新区', phone: '02198765432', social_credit_code: null },
  ]

  it('renders table headers', () => {
    render(<LawFirmTable lawFirms={[]} />)
    expect(screen.getByText('律所名称')).toBeInTheDocument()
    expect(screen.getByText('地址')).toBeInTheDocument()
    expect(screen.getByText('联系电话')).toBeInTheDocument()
    expect(screen.getByText('统一社会信用代码')).toBeInTheDocument()
  })

  it('renders law firm data rows', () => {
    render(<LawFirmTable lawFirms={mockFirms as any} />)
    expect(screen.getByText('大成律所')).toBeInTheDocument()
    expect(screen.getByText('金杜律所')).toBeInTheDocument()
  })

  it('renders empty state when no firms', () => {
    render(<LawFirmTable lawFirms={[]} />)
    expect(screen.getByText('暂无律所数据')).toBeInTheDocument()
  })

  it('masks social credit code', () => {
    render(<LawFirmTable lawFirms={mockFirms as any} />)
    expect(screen.getByText('9111****6789')).toBeInTheDocument()
  })

  it('shows skeleton when loading', () => {
    const { container } = render(<LawFirmTable lawFirms={[]} isLoading />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })
})
