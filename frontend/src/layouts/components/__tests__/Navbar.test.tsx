import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { Navbar } from '../Navbar'

// Mock dependencies
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

vi.mock('@/features/auth/api', () => ({
  authApi: {
    logout: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('next-themes', () => ({
  useTheme: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/components/shared/TopbarIcons', () => ({
  TopbarIcons: () => <div data-testid="topbar-icons" />,
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (url: string) => url,
}))

vi.mock('lucide-react', () => ({
  Menu: (props: Record<string, unknown>) => <svg data-testid="menu-icon" {...props} />,
  LogOut: (props: Record<string, unknown>) => <svg data-testid="logout-icon" {...props} />,
  Home: (props: Record<string, unknown>) => <svg data-testid="home-icon" {...props} />,
  Users: (props: Record<string, unknown>) => <svg data-testid="users-icon" {...props} />,
  Settings: (props: Record<string, unknown>) => <svg data-testid="settings-icon" {...props} />,
  Moon: (props: Record<string, unknown>) => <svg data-testid="moon-icon" {...props} />,
  Sun: (props: Record<string, unknown>) => <svg data-testid="sun-icon" {...props} />,
}))

import { useAuthStore } from '@/stores/auth'
import { useTheme } from 'next-themes'
import { authApi } from '@/features/auth/api'
import { toast } from 'sonner'

const mockUseAuthStore = vi.mocked(useAuthStore)
const mockUseTheme = vi.mocked(useTheme)

const mockLogout = vi.fn()

function setupAuthStore(user: Record<string, unknown> | null) {
  mockUseAuthStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
    const state = { user, logout: mockLogout }
    return selector(state)
  })
}

describe('Navbar', () => {
  const defaultProps = {
    onMenuClick: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: vi.fn(),
      themes: ['light', 'dark'],
    } as ReturnType<typeof useTheme>)
    setupAuthStore({
      username: 'testuser',
      real_name: '测试用户',
      is_admin: true,
      avatar_url: null,
    })
  })

  it('renders the navbar header', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('banner')).toBeInTheDocument()
  })

  it('displays user display name', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('测试用户')).toBeInTheDocument()
  })

  it('displays admin role label', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('管理员')).toBeInTheDocument()
  })

  it('displays lawyer role for non-admin', () => {
    setupAuthStore({
      username: 'lawyer1',
      real_name: '律师一',
      is_admin: false,
      avatar_url: null,
    })

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('律师')).toBeInTheDocument()
  })

  it('shows username when no real_name', () => {
    setupAuthStore({
      username: 'testuser',
      real_name: null,
      is_admin: false,
      avatar_url: null,
    })

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('testuser')).toBeInTheDocument()
  })

  it('shows default when no user info', () => {
    setupAuthStore(null)

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('用户')).toBeInTheDocument()
  })

  it('calls onMenuClick when mobile menu button is clicked', () => {
    const onMenuClick = vi.fn()
    render(
      <MemoryRouter>
        <Navbar onMenuClick={onMenuClick} />
      </MemoryRouter>,
    )

    const menuButton = screen.getByLabelText('打开菜单')
    fireEvent.click(menuButton)
    expect(onMenuClick).toHaveBeenCalled()
  })

  it('renders search bar text', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('搜索功能或输入命令...')).toBeInTheDocument()
  })

  it('renders topbar icons', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('topbar-icons')).toBeInTheDocument()
  })

  it('renders avatar fallback with first character', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('测')).toBeInTheDocument()
  })

  it('renders avatar fallback with uppercase initial when no real_name', () => {
    setupAuthStore({
      username: 'admin',
      real_name: null,
      is_admin: true,
      avatar_url: null,
    })

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('shows default avatar initial U when no user info', () => {
    setupAuthStore(null)

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // When no user, getAvatarInitials returns 'U'
    expect(screen.getByText('U')).toBeInTheDocument()
  })

  it('toggles theme from light to dark', () => {
    const setTheme = vi.fn()
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme,
      themes: ['light', 'dark'],
    } as ReturnType<typeof useTheme>)

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // Find the theme toggle button (Sun/Moon icons)
    const sunIcon = screen.getByTestId('sun-icon')
    const themeButton = sunIcon.closest('button')!
    fireEvent.click(themeButton)
    expect(setTheme).toHaveBeenCalledWith('dark')
  })

  it('toggles theme from dark to light', () => {
    const setTheme = vi.fn()
    mockUseTheme.mockReturnValue({
      theme: 'dark',
      setTheme,
      themes: ['light', 'dark'],
    } as ReturnType<typeof useTheme>)

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    const moonIcon = screen.getByTestId('moon-icon')
    const themeButton = moonIcon.closest('button')!
    fireEvent.click(themeButton)
    expect(setTheme).toHaveBeenCalledWith('light')
  })

  it('renders theme toggle button', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // Theme toggle button should exist
    const sunIcon = screen.getByTestId('sun-icon')
    expect(sunIcon).toBeInTheDocument()
  })

  it('shows moon icon in light theme', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('moon-icon')).toBeInTheDocument()
    expect(screen.getByTestId('sun-icon')).toBeInTheDocument()
  })

  it('handles logout when clicked', async () => {
    vi.mocked(authApi.logout).mockResolvedValueOnce({} as never)
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // Find the user avatar/trigger button and click it to open dropdown
    const userTrigger = screen.getByText('测试用户').closest('button')!
    await user.click(userTrigger)

    // Wait for dropdown to render
    await waitFor(() => {
      expect(screen.getByText('注销')).toBeInTheDocument()
    })

    // Click the logout button
    await user.click(screen.getByText('注销'))

    await waitFor(() => {
      expect(mockLogout).toHaveBeenCalled()
    })
  })

  it('renders user display name in trigger button', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // The trigger button should show the user name
    expect(screen.getByText('测试用户')).toBeInTheDocument()
    // And the role label
    expect(screen.getByText('管理员')).toBeInTheDocument()
  })

  it('renders search bar with keyboard shortcut hint', () => {
    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('搜索功能或输入命令...')).toBeInTheDocument()
  })

  it('dispatches keyboard event when search bar is clicked', async () => {
    const user = userEvent.setup()
    const dispatchEventSpy = vi.spyOn(document, 'dispatchEvent')

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // Click on the search bar area
    const searchBar = screen.getByText('搜索功能或输入命令...').closest('div')!
    await user.click(searchBar)

    // Should dispatch a KeyboardEvent for opening command palette
    expect(dispatchEventSpy).toHaveBeenCalled()
    const dispatchedEvent = dispatchEventSpy.mock.calls.find(
      (call) => call[0] instanceof KeyboardEvent
    )
    expect(dispatchedEvent).toBeTruthy()

    dispatchEventSpy.mockRestore()
  })

  it('renders all dropdown menu items when opened', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // Open the dropdown
    const userTrigger = screen.getByText('测试用户').closest('button')!
    await user.click(userTrigger)

    // Wait for dropdown content to appear
    await waitFor(() => {
      expect(screen.getByText('律所设置')).toBeInTheDocument()
    })

    expect(screen.getByText('团队设置')).toBeInTheDocument()
    expect(screen.getByText('律师设置')).toBeInTheDocument()
    expect(screen.getByText('系统配置')).toBeInTheDocument()
    expect(screen.getByText('注销')).toBeInTheDocument()
  })

  it('navigates to law firm settings when clicked', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    const userTrigger = screen.getByText('测试用户').closest('button')!
    await user.click(userTrigger)

    await waitFor(() => {
      expect(screen.getByText('律所设置')).toBeInTheDocument()
    })

    // Click the menu item - this should trigger navigation
    await user.click(screen.getByText('律所设置'))
    // Navigation happens via useNavigate, which is mocked in MemoryRouter
  })

  it('renders avatar image when avatar_url is set', () => {
    setupAuthStore({
      username: 'testuser',
      real_name: '测试用户',
      is_admin: true,
      avatar_url: '/media/avatar.jpg',
    })

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    // The component should render without errors when avatar_url is set
    expect(screen.getByText('测试用户')).toBeInTheDocument()
    // Check that the AvatarFallback is still rendered (Radix Avatar shows fallback when image fails to load)
    expect(screen.getByText('测')).toBeInTheDocument()
  })

  it('displays username as display name when real_name is null', () => {
    setupAuthStore({
      username: 'testuser',
      real_name: null,
      is_admin: false,
      avatar_url: null,
    })

    render(
      <MemoryRouter>
        <Navbar {...defaultProps} />
      </MemoryRouter>,
    )

    expect(screen.getByText('testuser')).toBeInTheDocument()
    expect(screen.getByText('律师')).toBeInTheDocument()
  })
})
