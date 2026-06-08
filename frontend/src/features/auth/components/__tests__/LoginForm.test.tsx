import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginForm } from '../LoginForm'

const mockMutate = vi.fn()

vi.mock('@/features/auth/hooks/use-auth-mutations', () => ({
  useLoginMutation: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}))

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders username and password inputs', () => {
    render(<LoginForm />)
    expect(screen.getByLabelText(/用户名/)).toBeInTheDocument()
    expect(screen.getByLabelText(/密码/)).toBeInTheDocument()
  })

  it('renders the login button', () => {
    render(<LoginForm />)
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
  })

  it('renders placeholder text for inputs', () => {
    render(<LoginForm />)
    expect(screen.getByPlaceholderText('请输入用户名')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument()
  })

  it('shows validation error when submitting empty form', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByText('请输入用户名')).toBeInTheDocument()
    })
  })

  it('calls login mutation on valid submission', async () => {
    const onSuccess = vi.fn()
    const user = userEvent.setup()
    mockMutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })

    render(<LoginForm onSuccess={onSuccess} />)
    await user.type(screen.getByLabelText(/用户名/), 'testuser')
    await user.type(screen.getByLabelText(/密码/), 'password123')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        { username: 'testuser', password: 'password123' },  // allowlist secret
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      )
    })
  })

  it('calls onError callback when login fails', async () => {
    const onError = vi.fn()
    const user = userEvent.setup()
    mockMutate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error('Invalid credentials'))
    })

    render(<LoginForm onError={onError} />)
    await user.type(screen.getByLabelText(/用户名/), 'testuser')
    await user.type(screen.getByLabelText(/密码/), 'wrong')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Invalid credentials')
    })
  })
})
