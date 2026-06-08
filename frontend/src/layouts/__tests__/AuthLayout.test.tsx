import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AuthLayout, AuthLayoutCard } from '../AuthLayout'

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => {
      // Filter out framer-motion specific props
      const { initial, animate, transition, whileHover, whileTap, ...rest } = props as Record<string, unknown>
      return <div {...rest}>{children as React.ReactNode}</div>
    },
  },
}))

// Mock ThemeToggle
vi.mock('@/features/auth/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Theme</button>,
}))

describe('AuthLayout', () => {
  it('renders the layout with outlet', () => {
    render(
      <MemoryRouter>
        <AuthLayout />
      </MemoryRouter>,
    )

    // ThemeToggle should be rendered
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
  })

  it('renders theme toggle button', () => {
    render(
      <MemoryRouter>
        <AuthLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('Theme')).toBeInTheDocument()
  })

  it('has min-h-screen class for full height', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthLayout />
      </MemoryRouter>,
    )

    const outerDiv = container.firstChild as HTMLElement
    expect(outerDiv.className).toContain('min-h-screen')
  })
})

describe('AuthLayoutCard', () => {
  it('renders children', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard>
          <div>Card Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    expect(screen.getByText('Card Content')).toBeInTheDocument()
  })

  it('renders title when provided', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard title="登录">
          <div>Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    expect(screen.getByText('登录')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard title="登录" description="请输入账号密码">
          <div>Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    expect(screen.getByText('请输入账号密码')).toBeInTheDocument()
  })

  it('does not render title/description when not provided', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard>
          <div>Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    // No card header text
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('renders title without description', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard title="注册">
          <div>Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    expect(screen.getByText('注册')).toBeInTheDocument()
  })

  it('renders description without title', () => {
    render(
      <MemoryRouter>
        <AuthLayoutCard description="some description">
          <div>Content</div>
        </AuthLayoutCard>
      </MemoryRouter>,
    )

    expect(screen.getByText('some description')).toBeInTheDocument()
  })
})
