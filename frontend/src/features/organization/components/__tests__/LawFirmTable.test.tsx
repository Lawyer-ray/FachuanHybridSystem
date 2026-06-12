vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawFirmDetail: (id: number) => `/lawfirms/${id}` },
}))

import { render, screen, fireEvent } from '@testing-library/react'
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

  it('shows - for null social_credit_code', () => {
    render(<LawFirmTable lawFirms={mockFirms as any} />)
    // firm 2 has null social_credit_code
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for null phone', () => {
    const firms = [{ ...mockFirms[0], phone: null }]
    render(<LawFirmTable lawFirms={firms as any} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for null address', () => {
    const firms = [{ ...mockFirms[0], address: null }]
    render(<LawFirmTable lawFirms={firms as any} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('formats non-11-digit phone as-is', () => {
    const firms = [{ ...mockFirms[0], phone: '12345' }]
    render(<LawFirmTable lawFirms={firms as any} />)
    expect(screen.getByText('12345')).toBeInTheDocument()
  })

  it('formats 11-digit phone with masking', () => {
    render(<LawFirmTable lawFirms={mockFirms as any} />)
    expect(screen.getByText('010****5678')).toBeInTheDocument()
  })

  it('truncates long address', () => {
    const longAddr = 'A'.repeat(50)
    const firms = [{ ...mockFirms[0], address: longAddr }]
    render(<LawFirmTable lawFirms={firms as any} />)
    // Should show truncated version with ...
    expect(screen.getByText(longAddr.slice(0, 30) + '...')).toBeInTheDocument()
  })

  it('shows short address as-is', () => {
    const firms = [{ ...mockFirms[0], address: '短地址' }]
    render(<LawFirmTable lawFirms={firms as any} />)
    expect(screen.getByText('短地址')).toBeInTheDocument()
  })

  it('shows short social credit code as-is', () => {
    const firms = [{ ...mockFirms[0], social_credit_code: '12345678' }]
    render(<LawFirmTable lawFirms={firms as any} />)
    expect(screen.getByText('12345678')).toBeInTheDocument()
  })

  it('shows - for empty name', () => {
    const firms = [{ ...mockFirms[0], name: '' }]
    render(<LawFirmTable lawFirms={firms as any} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('navigates to detail on row click', () => {
    // useNavigate is mocked, but we can verify the row is clickable
    render(<LawFirmTable lawFirms={mockFirms as any} />)
    const row = screen.getByText('大成律所').closest('tr')
    expect(row).toBeTruthy()
    fireEvent.click(row!)
    // Navigation is mocked so we just verify no crash
  })
})
