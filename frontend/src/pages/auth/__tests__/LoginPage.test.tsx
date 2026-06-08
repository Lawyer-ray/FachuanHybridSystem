import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { LoginPage } from '../LoginPage'

const mockNavigate = vi.fn()

// Mock dependencies
vi.mock('@/features/auth/components/LoginForm', () => ({
  LoginForm: ({ onSuccess, onError }: { onSuccess: () => void; onError: (e: string) => void }) => (
    <div data-testid="login-form">
      <button onClick={onSuccess}>Login</button>
      <button onClick={() => onError('test error')}>Fail</button>
    </div>
  ),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock AuthLayoutCard to render children directly
vi.mock('@/layouts/AuthLayout', () => ({
  AuthLayoutCard: ({ children, title, description }: { children: React.ReactNode; title?: string; description?: string }) => (
    <div data-testid="auth-layout-card">
      {title && <h2>{title}</h2>}
      {description && <p>{description}</p>}
      {children}
    </div>
  ),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  }
})

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the login form', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('login-form')).toBeInTheDocument()
  })

  it('renders title "登录"', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('登录')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('欢迎回来，请登录您的账号')).toBeInTheDocument()
  })

  it('renders forgot password link', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('忘记密码？')).toBeInTheDocument()
  })

  it('renders register link', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('立即注册')).toBeInTheDocument()
    expect(screen.getByText('还没有账号？')).toBeInTheDocument()
  })

  it('forgot password link points to correct path', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    const link = screen.getByText('忘记密码？').closest('a')
    expect(link).toHaveAttribute('href', '/forgot-password')
  })

  it('register link points to correct path', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    const link = screen.getByText('立即注册').closest('a')
    expect(link).toHaveAttribute('href', '/register')
  })

  it('calls navigate with /dashboard on success without redirect param', async () => {
    const { toast } = await import('sonner')

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText('Login'))
    expect(toast.success).toHaveBeenCalledWith('登录成功')
    expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true })
  })

  it('calls toast.error on login error', async () => {
    const { toast } = await import('sonner')

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText('Fail'))
    expect(toast.error).toHaveBeenCalledWith('test error')
  })
})
