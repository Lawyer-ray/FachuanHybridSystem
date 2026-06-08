vi.mock('../../hooks/use-lawfirm', () => ({ useLawFirm: vi.fn() }))
vi.mock('../../hooks/use-lawfirm-mutations', () => ({
  useLawFirmMutations: () => ({
    createLawFirm: { mutate: vi.fn(), isPending: false },
    updateLawFirm: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { lawFirmDetail: (id: number) => `/lawfirms/${id}` },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { LawFirmForm } from '../LawFirmForm'
import { useLawFirm } from '../../hooks/use-lawfirm'

describe('LawFirmForm', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders form title in create mode', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText('律所信息')).toBeInTheDocument()
  })

  it('renders all form fields', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawFirmForm mode="create" />)
    expect(screen.getByPlaceholderText('请输入律所名称')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入联系电话')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入律所地址')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入统一社会信用代码')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入开户行名称')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入银行账号')).toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    render(<LawFirmForm mode="create" />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('shows loading spinner in edit mode while loading', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    const { container } = render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(container.querySelector('[class*="animate-spin"]')).toBeInTheDocument()
  })

  it('shows error in edit mode on error', () => {
    vi.mocked(useLawFirm).mockReturnValue({ data: undefined, isLoading: false, error: new Error('fail') } as any)
    render(<LawFirmForm lawFirmId="1" mode="edit" />)
    expect(screen.getByText('加载律所数据失败')).toBeInTheDocument()
  })
})
