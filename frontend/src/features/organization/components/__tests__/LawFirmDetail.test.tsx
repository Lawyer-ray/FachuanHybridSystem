vi.mock('../../hooks/use-lawfirm', () => ({
  useLawFirm: vi.fn(),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_ORGANIZATION: '/organization' },
  generatePath: { lawFirmEdit: (id: string) => `/lawfirms/${id}/edit` },
}))

import { render, screen } from '@testing-library/react'
import { LawFirmDetail } from '../LawFirmDetail'
import { useLawFirm } from '../../hooks/use-lawfirm'

const mockFirm = {
  id: 1, name: '大成律所', address: '北京市朝阳区', phone: '01012345678',
  social_credit_code: '91110000MA01234567', bank_name: '工商银行', bank_account: '6222000000000000',
}

describe('LawFirmDetail', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows loading skeleton', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    const { container } = render(<LawFirmDetail lawFirmId="1" />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('shows not found when error', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: false, error: new Error('404') } as any)
    render(<LawFirmDetail lawFirmId="1" />)
    expect(screen.getByText('律所不存在')).toBeInTheDocument()
  })

  it('renders firm info when loaded', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: mockFirm, isLoading: false, error: null } as any)
    render(<LawFirmDetail lawFirmId="1" />)
    expect(screen.getAllByText('大成律所').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('displays firm details', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: mockFirm, isLoading: false, error: null } as any)
    render(<LawFirmDetail lawFirmId="1" />)
    expect(screen.getByText('北京市朝阳区')).toBeInTheDocument()
    expect(screen.getByText('工商银行')).toBeInTheDocument()
  })
})
