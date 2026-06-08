import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AdminLayout } from '../AdminLayout'

// Mock dependencies
vi.mock('@/stores/ui', () => ({
  useUIStore: vi.fn(),
}))

vi.mock('@/contexts/BreadcrumbContext', async () => {
  const { createContext, useContext } = await import('react')
  const ctx = createContext({ customItems: null, setCustomItems: vi.fn() })
  return {
    BreadcrumbProvider: ({ children }: { children: React.ReactNode }) => (
      <ctx.Provider value={{ customItems: null, setCustomItems: vi.fn() }}>
        {children}
      </ctx.Provider>
    ),
    useBreadcrumbContext: () => useContext(ctx),
  }
})

vi.mock('@/layouts/components/Sidebar', () => ({
  Sidebar: ({ collapsed }: { collapsed: boolean }) => (
    <div data-testid="sidebar" data-collapsed={collapsed}>Sidebar</div>
  ),
}))

vi.mock('@/layouts/components/Navbar', () => ({
  Navbar: ({ onMenuClick }: { onMenuClick: () => void }) => (
    <header data-testid="navbar">
      <button onClick={onMenuClick}>Menu</button>
    </header>
  ),
}))

vi.mock('@/layouts/components/Breadcrumb', () => ({
  Breadcrumb: ({ items }: { items: Array<{ label: string }> }) => (
    <nav data-testid="breadcrumb">
      {items.map((item, i) => <span key={i}>{item.label}</span>)}
    </nav>
  ),
}))

vi.mock('@/components/shared/CommandPalette', () => ({
  CommandPalette: () => <div data-testid="command-palette" />,
}))

vi.mock('@/components/shared/PageSkeleton', () => ({
  PageSkeleton: () => <div data-testid="page-skeleton" />,
}))

import { useUIStore } from '@/stores/ui'

const mockUseUIStore = vi.mocked(useUIStore)

function setupStore(overrides: Record<string, unknown> = {}) {
  const defaults = {
    sidebarCollapsed: false,
    toggleSidebar: vi.fn(),
    setSidebarCollapsed: vi.fn(),
    ...overrides,
  }

  mockUseUIStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
    return selector(defaults)
  })

  return defaults
}

describe('AdminLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupStore()
  })

  it('renders sidebar', () => {
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('sidebar')).toBeInTheDocument()
  })

  it('renders navbar', () => {
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('navbar')).toBeInTheDocument()
  })

  it('renders breadcrumb', () => {
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
  })

  it('renders command palette', () => {
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('command-palette')).toBeInTheDocument()
  })

  it('sidebar receives collapsed state from store', () => {
    setupStore({ sidebarCollapsed: true })

    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('sidebar')).toHaveAttribute('data-collapsed', 'true')
  })

  it('sidebar is expanded by default', () => {
    setupStore({ sidebarCollapsed: false })

    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('sidebar')).toHaveAttribute('data-collapsed', 'false')
  })

  it('renders main content area', () => {
    const { container } = render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    const main = container.querySelector('main')
    expect(main).toBeInTheDocument()
  })

  it('generates breadcrumb for dashboard path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('首页')).toBeInTheDocument()
  })

  it('generates breadcrumb for cases path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases']}>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('首页')).toBeInTheDocument()
    expect(screen.getByText('案件')).toBeInTheDocument()
  })

  it('generates breadcrumb for clients path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/clients']}>
        <AdminLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('当事人')).toBeInTheDocument()
  })

  it('has bg-background class', () => {
    const { container } = render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain('bg-background')
    expect(wrapper.className).toContain('min-h-screen')
  })
})
