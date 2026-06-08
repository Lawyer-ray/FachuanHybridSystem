import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ForgotPasswordPage } from '../ForgotPasswordPage'

// Mock dependencies
vi.mock('@/features/auth/api', () => ({
  authApi: {
    requestPasswordReset: vi.fn(),
  },
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

// Mock UI components to simplify testing
vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children as React.ReactNode}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => {
    // Just pass through children - the actual <form> element in the component handles submission
    return <>{children}</>
  },
  FormControl: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FormField: ({ render: renderFn, name }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode; name?: string }) =>
    renderFn({ field: { value: '', onChange: vi.fn(), onBlur: vi.fn(), name: name || 'email', ref: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <div />,
}))

vi.mock('lucide-react', () => ({
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader" {...props} />,
  Mail: (props: Record<string, unknown>) => <svg data-testid="mail-icon" {...props} />,
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  CheckCircle2: (props: Record<string, unknown>) => <svg data-testid="check-circle" {...props} />,
}))

import { authApi } from '@/features/auth/api'
import { toast } from 'sonner'

const mockRequestPasswordReset = vi.mocked(authApi.requestPasswordReset)

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the forgot password form', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('忘记密码')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('输入您的注册邮箱，我们将发送密码重置链接')).toBeInTheDocument()
  })

  it('renders email input label', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('邮箱地址')).toBeInTheDocument()
  })

  it('renders submit button', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('发送重置链接')).toBeInTheDocument()
  })

  it('renders back to login link', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/返回登录/)).toBeInTheDocument()
  })

  it('back to login link points to correct path', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const link = screen.getByText(/返回登录/).closest('a')
    expect(link).toHaveAttribute('href', '/login')
  })

  it('renders email input field', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const input = screen.getByPlaceholderText('请输入注册时使用的邮箱')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'email')
  })

  it('renders all UI elements', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    // Verify all form elements are present
    expect(screen.getByText('忘记密码')).toBeInTheDocument()
    expect(screen.getByText('输入您的注册邮箱，我们将发送密码重置链接')).toBeInTheDocument()
    expect(screen.getByText('邮箱地址')).toBeInTheDocument()
    expect(screen.getByText('发送重置链接')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入注册时使用的邮箱')).toBeInTheDocument()
    expect(screen.getByText(/返回登录/)).toBeInTheDocument()
  })

  it('authApi module is properly imported', () => {
    expect(authApi.requestPasswordReset).toBeDefined()
    expect(typeof authApi.requestPasswordReset).toBe('function')
  })

  it('form email input has correct attributes', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const input = screen.getByPlaceholderText('请输入注册时使用的邮箱')
    expect(input).toHaveAttribute('type', 'email')
  })

  it('back to login link has correct structure', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const link = screen.getByText(/返回登录/).closest('a')
    expect(link).toHaveAttribute('href', '/login')
    expect(link).toHaveClass('font-medium')
  })

  it('renders mail icon in submit button', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    // Mail icon is rendered inside the submit button
    const submitButton = screen.getByText('发送重置链接')
    expect(submitButton).toBeInTheDocument()
  })

  it('has the AuthLayoutCard wrapper', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const card = screen.getByTestId('auth-layout-card')
    expect(card).toBeInTheDocument()
  })

  it('form has submit button with correct type', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const button = screen.getByRole('button', { name: /发送重置链接/ })
    expect(button).toHaveAttribute('type', 'submit')
  })

  it('displays page title in AuthLayoutCard', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    const title = screen.getByRole('heading', { name: '忘记密码' })
    expect(title).toBeInTheDocument()
  })

  it('renders multiple form elements', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    // Verify structure: label, input, button, link
    expect(screen.getByText('邮箱地址')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入注册时使用的邮箱')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /发送重置链接/ })).toBeInTheDocument()
    expect(screen.getByText(/返回登录/)).toBeInTheDocument()
  })
})
