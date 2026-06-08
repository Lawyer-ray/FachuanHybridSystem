const mockNavigate = vi.fn()

import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { RegisterPage } from '../RegisterPage'

// Mock dependencies
vi.mock('@/features/auth/components/RegisterForm', () => ({
  RegisterForm: ({ onSuccess, onError }: { onSuccess: (requiresApproval: boolean) => void; onError: (e: string) => void }) => (
    <div data-testid="register-form">
      <button onClick={() => onSuccess(false)}>Register First User</button>
      <button onClick={() => onSuccess(true)}>Register Subsequent User</button>
      <button onClick={() => onError('error')}>Fail</button>
    </div>
  ),
}))

vi.mock('@/features/auth/components/PendingApproval', () => ({
  PendingApproval: () => <div data-testid="pending-approval">等待审批</div>,
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

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
  }
})

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the register form initially', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('register-form')).toBeInTheDocument()
  })

  it('renders title "注册"', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('注册')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('创建您的账号')).toBeInTheDocument()
  })

  it('renders login link', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('立即登录')).toBeInTheDocument()
    expect(screen.getByText('已有账号？')).toBeInTheDocument()
  })

  it('login link points to correct path', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    const link = screen.getByText('立即登录').closest('a')
    expect(link).toHaveAttribute('href', '/login')
  })

  it('shows pending approval when registration requires approval', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    // Click button that triggers onSuccess(true) -> shows pending approval
    fireEvent.click(screen.getByText('Register Subsequent User'))

    // The component should re-render with PendingApproval
    expect(screen.getByTestId('pending-approval')).toBeInTheDocument()
    // Title "等待审批" should also appear
    expect(screen.getByRole('heading', { name: '等待审批' })).toBeInTheDocument()
  })

  it('does not show pending approval initially', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    expect(screen.queryByTestId('pending-approval')).not.toBeInTheDocument()
  })

  it('renders register form with correct structure', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    // AuthLayoutCard should be rendered
    expect(screen.getByTestId('auth-layout-card')).toBeInTheDocument()
    // Register form should be present
    expect(screen.getByTestId('register-form')).toBeInTheDocument()
  })

  it('navigates to /dashboard for first user (no approval needed)', async () => {
    const { toast } = await import('sonner')

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText('Register First User'))
    expect(toast.success).toHaveBeenCalledWith('注册成功，您是首位用户，已自动成为管理员')
    expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
  })

  it('calls toast.error on registration error', async () => {
    const { toast } = await import('sonner')

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText('Fail'))
    expect(toast.error).toHaveBeenCalledWith('error')
  })

  it('hides register form after pending approval is shown', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText('Register Subsequent User'))
    expect(screen.queryByTestId('register-form')).not.toBeInTheDocument()
    expect(screen.getByTestId('pending-approval')).toBeInTheDocument()
  })
})
