import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Breadcrumb, type BreadcrumbItem } from '../Breadcrumb'

// Mock lucide-react
vi.mock('lucide-react', () => ({
  ChevronRight: (props: Record<string, unknown>) => <span data-testid="chevron" {...props} />,
  Home: (props: Record<string, unknown>) => <span data-testid="home-icon" {...props} />,
}))

describe('Breadcrumb', () => {
  it('renders nothing when items is empty', () => {
    const { container } = render(
      <MemoryRouter>
        <Breadcrumb items={[]} />
      </MemoryRouter>,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when items is undefined/null', () => {
    const { container } = render(
      <MemoryRouter>
        <Breadcrumb items={null as unknown as BreadcrumbItem[]} />
      </MemoryRouter>,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders a single item with home icon', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[{ label: '首页' }]} />
      </MemoryRouter>,
    )

    expect(screen.getByText('首页')).toBeInTheDocument()
    expect(screen.getByTestId('home-icon')).toBeInTheDocument()
  })

  it('renders multiple items with chevron separators', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[
          { label: '首页', path: '/admin/dashboard' },
          { label: '当事人' },
        ]} />
      </MemoryRouter>,
    )

    expect(screen.getByText('首页')).toBeInTheDocument()
    expect(screen.getByText('当事人')).toBeInTheDocument()
    // 1 chevron separator between 2 items
    expect(screen.getByTestId('chevron')).toBeInTheDocument()
  })

  it('renders link for items with path (except last)', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[
          { label: '首页', path: '/admin/dashboard' },
          { label: '当事人', path: '/admin/clients' },
          { label: '张三' },
        ]} />
      </MemoryRouter>,
    )

    // First two items should be links
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', '/admin/dashboard')
    expect(links[1]).toHaveAttribute('href', '/admin/clients')
  })

  it('last item is rendered as text, not a link', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[
          { label: '首页', path: '/admin/dashboard' },
          { label: '当事人' },
        ]} />
      </MemoryRouter>,
    )

    // Only the first item is a link
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)

    // Last item is a span with aria-current="page"
    const currentPage = screen.getByText('当事人')
    expect(currentPage).toHaveAttribute('aria-current', 'page')
  })

  it('renders nav with correct aria-label', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[{ label: '首页' }]} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('navigation', { name: '面包屑导航' })).toBeInTheDocument()
  })

  it('renders four-level breadcrumb correctly', () => {
    render(
      <MemoryRouter>
        <Breadcrumb items={[
          { label: '首页', path: '/admin/dashboard' },
          { label: '组织管理', path: '/admin/organization' },
          { label: '律所', path: '/admin/organization/lawfirms' },
          { label: '编辑' },
        ]} />
      </MemoryRouter>,
    )

    expect(screen.getByText('首页')).toBeInTheDocument()
    expect(screen.getByText('组织管理')).toBeInTheDocument()
    expect(screen.getByText('律所')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()

    // 3 chevron separators for 4 items
    const chevrons = screen.getAllByTestId('chevron')
    expect(chevrons).toHaveLength(3)

    // 3 links (last item is text)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(3)
  })
})
