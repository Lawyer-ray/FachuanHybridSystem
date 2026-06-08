import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { AuthGuard, GuestGuard } from '../guards'

// Mock useAuth hook
vi.mock('@/features/auth/hooks/use-auth', () => ({
  useAuth: vi.fn(),
}))

// Mock Loader2 icon
vi.mock('lucide-react', () => ({
  Loader2: (props: Record<string, unknown>) => <div data-testid="loader2" {...props} />,
}))

import { useAuth } from '@/features/auth/hooks/use-auth'
const mockUseAuth = vi.mocked(useAuth)

describe('AuthGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton when isLoading is true', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/admin/dashboard" element={<div>Dashboard</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('验证登录状态...')).toBeInTheDocument()
  })

  it('renders child route when authenticated', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/admin/dashboard" element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Dashboard Content')).toBeInTheDocument()
  })

  it('calls checkAuth on mount', () => {
    const checkAuth = vi.fn()
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      checkAuth,
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/admin/dashboard" element={<div>Dashboard</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(checkAuth).toHaveBeenCalled()
  })

  it('redirects to login when not authenticated and not loading', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/admin/cases']}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/admin/cases" element={<div>Cases</div>} />
          </Route>
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    // Should redirect to login page
    expect(screen.getByText('Login Page')).toBeInTheDocument()
  })
})

describe('GuestGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton when isLoading is true', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: true,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/login" element={<div>Login Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('验证登录状态...')).toBeInTheDocument()
  })

  it('renders child route when not authenticated', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/login" element={<div>Login Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Login Page')).toBeInTheDocument()
  })

  it('calls checkAuth on mount', () => {
    const checkAuth = vi.fn()
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      checkAuth,
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/login" element={<div>Login Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(checkAuth).toHaveBeenCalled()
  })

  it('redirects to dashboard when authenticated', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/login" element={<div>Login Page</div>} />
          </Route>
          <Route path="/admin/dashboard" element={<div>Dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    )

    // Should redirect to dashboard
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('redirects to specified redirect param when authenticated', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      checkAuth: vi.fn(),
    } as ReturnType<typeof useAuth>)

    render(
      <MemoryRouter initialEntries={['/login?redirect=/admin/cases']}>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/login" element={<div>Login Page</div>} />
          </Route>
          <Route path="/admin/cases" element={<div>Cases Page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    // Should redirect to the specified path
    expect(screen.getByText('Cases Page')).toBeInTheDocument()
  })
})
