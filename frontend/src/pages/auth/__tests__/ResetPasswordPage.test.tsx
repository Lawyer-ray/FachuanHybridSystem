import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ResetPasswordPage } from '../ResetPasswordPage'

// Mock dependencies
vi.mock('@/features/auth/api', () => ({
  authApi: {
    verifyPasswordResetToken: vi.fn().mockResolvedValue({
      success: true,
      data: { is_valid: true, username: 'testuser' },
    }),
    confirmPasswordReset: vi.fn().mockResolvedValue({ success: true }),
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

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children as React.ReactNode}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormControl: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FormField: ({ render: renderFn }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode }) =>
    renderFn({ field: { value: '', onChange: vi.fn(), onBlur: vi.fn(), name: 'password', ref: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <div />,
}))

vi.mock('lucide-react', () => ({
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader" {...props} />,
  CheckCircle2: (props: Record<string, unknown>) => <svg data-testid="check-circle" {...props} />,
  XCircle: (props: Record<string, unknown>) => <svg data-testid="x-circle" {...props} />,
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
}))

import { authApi } from '@/features/auth/api'
import { toast } from 'sonner'

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(authApi.verifyPasswordResetToken).mockResolvedValue({
      success: true,
      data: { is_valid: true, username: 'testuser' },
    })
    vi.mocked(authApi.confirmPasswordReset).mockResolvedValue({ success: true })
  })

  it('shows invalid token state when no params', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('链接无效')).toBeInTheDocument()
    })
  })

  it('shows invalid token message text', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('密码重置链接无效或已过期。')).toBeInTheDocument()
    })
  })

  it('shows reset password form when token is valid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    // Wait for the API call to resolve and form to appear
    await waitFor(() => {
      expect(screen.getByText('新密码')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows username in description when token is valid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/testuser/)).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows confirm password field', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('确认密码')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows back to login link when token is invalid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('重新申请重置')).toBeInTheDocument()
    })
  })

  it('shows 30 minute expiry info when token is invalid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/30 分钟/)).toBeInTheDocument()
    })
  })

  it('shows reset password button when token is valid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      const buttons = screen.getAllByText('重置密码')
      expect(buttons.length).toBeGreaterThanOrEqual(1)
      // Should have both title and button
      expect(buttons.some((el) => el.tagName === 'BUTTON')).toBe(true)
    }, { timeout: 3000 })
  })

  it('shows link to forgot-password when token is invalid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      const link = screen.getByText('重新申请重置').closest('a')
      expect(link).toHaveAttribute('href', '/forgot-password')
    })
  })

  it('handles verify token API failure gracefully', async () => {
    vi.mocked(authApi.verifyPasswordResetToken).mockRejectedValue(new Error('fail'))

    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('链接无效')).toBeInTheDocument()
    })
  })

  it('handles verify token returning invalid status', async () => {
    vi.mocked(authApi.verifyPasswordResetToken).mockResolvedValue({
      success: true,
      data: { is_valid: false },
    })

    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('链接无效')).toBeInTheDocument()
    })
  })

  it('shows loading state while verifying token', async () => {
    let resolveVerify: (v: unknown) => void
    vi.mocked(authApi.verifyPasswordResetToken).mockImplementation(
      () => new Promise((resolve) => { resolveVerify = resolve })
    )

    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('验证中')).toBeInTheDocument()
    expect(screen.getByText('正在验证重置链接...')).toBeInTheDocument()

    // Resolve to clean up
    resolveVerify!({ success: true, data: { is_valid: true, username: 'test' } })

    await waitFor(() => {
      expect(screen.getByText('新密码')).toBeInTheDocument()
    })
  })

  it('renders all form fields when token is valid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('新密码')).toBeInTheDocument()
      expect(screen.getByText('确认密码')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('至少8个字符')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('再次输入新密码')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('renders back to login link when token is valid', async () => {
    render(
      <MemoryRouter initialEntries={['/reset-password?uid=abc&token=xyz']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      const link = screen.getByText(/返回登录/).closest('a')
      expect(link).toHaveAttribute('href', '/login')
    }, { timeout: 3000 })
  })
})
