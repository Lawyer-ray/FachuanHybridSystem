import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RegisterForm } from '../RegisterForm'

const mockMutate = vi.fn()

vi.mock('@/features/auth/hooks/use-auth-mutations', () => ({
  useRegisterMutation: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}))

describe('RegisterForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all form fields', () => {
    render(<RegisterForm />)
    expect(screen.getByLabelText(/用户名/)).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
    expect(screen.getByLabelText(/确认密码/)).toBeInTheDocument()
    expect(screen.getByLabelText(/真实姓名/)).toBeInTheDocument()
    expect(screen.getByLabelText(/手机号/)).toBeInTheDocument()
  })

  it('renders the register button', () => {
    render(<RegisterForm />)
    expect(screen.getByRole('button', { name: '注册' })).toBeInTheDocument()
  })

  it('shows validation error for short username', async () => {
    const user = userEvent.setup()
    render(<RegisterForm />)
    await user.type(screen.getByLabelText(/用户名/), 'ab')
    await user.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => {
      expect(screen.getByText('用户名至少3个字符')).toBeInTheDocument()
    })
  })

  it('shows validation error for mismatched passwords', async () => {
    const user = userEvent.setup()
    render(<RegisterForm />)
    await user.type(screen.getByLabelText(/用户名/), 'testuser')
    await user.type(screen.getByLabelText('密码'), 'password123')
    await user.type(screen.getByLabelText(/确认密码/), 'different')
    await user.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => {
      expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument()
    })
  })

  it('calls register mutation with correct data on valid submission', async () => {
    const onSuccess = vi.fn()
    const user = userEvent.setup()
    mockMutate.mockImplementation((_data: unknown, opts: { onSuccess: (resp: { requires_approval: boolean }) => void }) => {
      opts.onSuccess({ requires_approval: false })
    })

    render(<RegisterForm onSuccess={onSuccess} />)
    await user.type(screen.getByLabelText(/用户名/), 'newuser')
    await user.type(screen.getByLabelText('密码'), 'password123')
    await user.type(screen.getByLabelText(/确认密码/), 'password123')
    await user.type(screen.getByLabelText(/真实姓名/), '张三')
    await user.click(screen.getByRole('button', { name: '注册' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          username: 'newuser',
          password: 'password123',
        }),
        expect.any(Object),
      )
    })
  })
})
