vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_LAWFIRM_NEW: '/lawfirms/new' },
}))

import { render, screen } from '@testing-library/react'
import { LawFirmList } from '../LawFirmList'
import { useLawFirms } from '../../hooks/use-lawfirms'

describe('LawFirmList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders create button', () => {
    render(<LawFirmList />)
    expect(screen.getByText('新建律所')).toBeInTheDocument()
  })

  it('shows empty state when no data', () => {
    vi.mocked(useLawFirms).mockReturnValue({ data: [], isLoading: false } as any)
    render(<LawFirmList />)
    expect(screen.getByText('暂无律所数据')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    vi.mocked(useLawFirms).mockReturnValue({ data: undefined, isLoading: true } as any)
    const { container } = render(<LawFirmList />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })
})
