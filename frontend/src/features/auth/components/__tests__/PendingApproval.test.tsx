import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { PendingApproval } from '../PendingApproval'

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <button {...props}>{children}</button>
  ),
}))

describe('PendingApproval', () => {
  const renderWithRouter = () =>
    render(
      <MemoryRouter>
        <PendingApproval />
      </MemoryRouter>,
    )

  it('renders the success heading', () => {
    renderWithRouter()
    expect(screen.getByText('注册成功')).toBeInTheDocument()
  })

  it('renders the approval message', () => {
    renderWithRouter()
    expect(screen.getByText(/您的账号正在等待管理员审批/)).toBeInTheDocument()
  })

  it('renders a link back to login', () => {
    renderWithRouter()
    const link = screen.getByRole('link', { name: '返回登录' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/login')
  })

  it('renders a clock icon', () => {
    const { container } = renderWithRouter()
    // The Clock icon renders as an SVG
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
