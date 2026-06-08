vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_LAWYER_NEW: '/lawyers/new' },
}))

import { render, screen } from '@testing-library/react'
import { LawyerList } from '../LawyerList'
import { useLawyers } from '../../hooks/use-lawyers'

describe('LawyerList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders create button', () => {
    render(<LawyerList />)
    expect(screen.getByText('新建律师')).toBeInTheDocument()
  })

  it('renders search filter', () => {
    render(<LawyerList />)
    expect(screen.getByPlaceholderText('搜索用户名、姓名、手机号...')).toBeInTheDocument()
  })

  it('shows empty state when no data', () => {
    vi.mocked(useLawyers).mockReturnValue({ data: [], isLoading: false } as any)
    render(<LawyerList />)
    expect(screen.getByText('暂无律师数据')).toBeInTheDocument()
  })
})
