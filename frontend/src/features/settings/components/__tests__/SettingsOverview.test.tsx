import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SettingsOverview } from '../SettingsOverview'

const mockNavigate = vi.fn()

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('@/routes/paths', () => ({
  PATHS: {
    ADMIN_SETTINGS: '/admin/settings',
    ADMIN_SETTINGS_LAW_FIRM: '/admin/settings/law-firm',
    ADMIN_SETTINGS_TEAM: '/admin/settings/team',
    ADMIN_SETTINGS_LAWYER: '/admin/settings/lawyer',
  },
}))

describe('SettingsOverview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderComponent = () =>
    render(
      <MemoryRouter>
        <SettingsOverview />
      </MemoryRouter>,
    )

  it('renders the page title', () => {
    renderComponent()
    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })

  it('renders the description', () => {
    renderComponent()
    expect(screen.getByText(/管理平台全局配置/)).toBeInTheDocument()
  })

  it('renders the search placeholder', () => {
    renderComponent()
    expect(screen.getByText('搜索设置项...')).toBeInTheDocument()
  })

  it('renders section headings', () => {
    renderComponent()
    expect(screen.getByText('机构管理')).toBeInTheDocument()
    expect(screen.getByText('消息平台')).toBeInTheDocument()
    expect(screen.getByText('AI 与数据服务')).toBeInTheDocument()
    expect(screen.getByText('系统')).toBeInTheDocument()
  })

  it('renders setting items', () => {
    renderComponent()
    expect(screen.getByText('律所设置')).toBeInTheDocument()
    expect(screen.getByText('团队设置')).toBeInTheDocument()
    expect(screen.getByText('律师设置')).toBeInTheDocument()
    expect(screen.getByText('飞书配置')).toBeInTheDocument()
    expect(screen.getByText('AI 服务配置')).toBeInTheDocument()
  })

  it('navigates when a setting item is clicked', async () => {
    const user = userEvent.setup()
    renderComponent()
    await user.click(screen.getByText('律所设置'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/settings/law-firm')
  })
})
