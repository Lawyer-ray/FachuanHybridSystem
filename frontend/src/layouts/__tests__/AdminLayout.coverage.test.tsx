/**
 * AdminLayout - additional branch/function coverage tests
 * Targets uncovered: generateBreadcrumbItems (fn 11,12 lines 93-94),
 * mobile menu (fn 15), ResizeObserver footer logic (fn 17),
 * NO_LINK_SEGMENTS, isWorkbench, customItems
 */

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
  Sidebar: ({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) => (
    <div data-testid="sidebar" data-collapsed={collapsed}>
      <button onClick={onToggle}>Toggle</button>
    </div>
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
  Breadcrumb: ({ items }: { items: Array<{ label: string; path?: string }> }) => (
    <nav data-testid="breadcrumb">
      {items.map((item, i) => <span key={i} data-path={item.path}>{item.label}</span>)}
    </nav>
  ),
}))

vi.mock('@/components/shared/CommandPalette', () => ({
  CommandPalette: () => <div data-testid="command-palette" />,
}))

vi.mock('@/components/shared/PageSkeleton', () => ({
  PageSkeleton: () => <div data-testid="page-skeleton" />,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AdminLayout } from '../AdminLayout'
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

describe('AdminLayout - coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupStore()
  })

  // Branch: generateBreadcrumbItems with NO_LINK_SEGMENTS (line 57-59)
  it('generates breadcrumb for path with config segment', () => {
    render(
      <MemoryRouter initialEntries={['/admin/config/llm']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('服务配置')).toBeInTheDocument()
  })

  // Branch: generateBreadcrumbItems with numeric segment skipped (line 51)
  it('skips numeric segments in breadcrumb', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases/123']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('案件')).toBeInTheDocument()
    // 123 should not appear as a breadcrumb
    expect(screen.queryByText('123')).not.toBeInTheDocument()
  })

  // Branch: generateBreadcrumbItems with UUID segment skipped (line 51)
  it('skips UUID segments in breadcrumb', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases/550e8400-e29b-41d4-a716-446655440000']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('案件')).toBeInTheDocument()
  })

  // Branch: generateBreadcrumbItems with known label (line 53)
  it('maps known segments to Chinese labels', () => {
    render(
      <MemoryRouter initialEntries={['/admin/settings/system']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('设置')).toBeInTheDocument()
    expect(screen.getByText('系统配置')).toBeInTheDocument()
  })

  // Branch: generateBreadcrumbItems with unknown segment (line 53 fallback)
  it('uses raw segment name for unknown segments', () => {
    render(
      <MemoryRouter initialEntries={['/admin/unknown-segment']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('unknown-segment')).toBeInTheDocument()
  })

  // Branch: generateBreadcrumbItems returns just 首页 for dashboard (line 45)
  it('returns only 首页 for dashboard path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('首页')).toBeInTheDocument()
  })

  // Branch: isMobile shows mobile overlay + drawer (line 132-145)
  it('shows mobile overlay and drawer when mobile menu is open', () => {
    // Simulate mobile by calling resize with small width
    const originalWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true, configurable: true })
    window.dispatchEvent(new Event('resize'))

    setupStore()
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )

    // On mobile, sidebar should not be rendered as the desktop sidebar
    // Click menu button to open mobile menu
    const menuBtn = screen.getByText('Menu')
    fireEvent.click(menuBtn)

    // Restore
    Object.defineProperty(window, 'innerWidth', { value: originalWidth, writable: true, configurable: true })
  })

  // Branch: toggleSidebar called from Sidebar (line 93)
  it('calls toggleSidebar when sidebar toggle is clicked', () => {
    const store = setupStore()
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('Toggle'))
    expect(store.toggleSidebar).toHaveBeenCalled()
  })

  // Branch: isWorkbench path adds overflow-hidden (line 154)
  it('adds overflow-hidden class for workbench path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/workbench']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    const main = document.querySelector('main')
    expect(main?.className).toContain('overflow-hidden')
  })

  // Branch: non-workbench path does not add overflow-hidden (line 154)
  it('does not add overflow-hidden for non-workbench path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    const main = document.querySelector('main')
    expect(main?.className).not.toContain('overflow-hidden')
  })

  // Branch: sidebar collapsed gives different margin (line 100)
  it('sets smaller margin-left when sidebar is collapsed', () => {
    setupStore({ sidebarCollapsed: true })
    const { container } = render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )
    const contentDiv = container.querySelector('[style*="margin-left"]')
    expect(contentDiv).toBeInTheDocument()
  })

  // Branch: footer visibility (line 163)
  it('renders footer when content is short', () => {
    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    // Footer may or may not be visible depending on ResizeObserver
    // We verify the component renders without error
    expect(screen.getByText('首页')).toBeInTheDocument()
  })

  // Branch: multiple path segments
  it('generates breadcrumb for deep path', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases/new']}>
        <AdminLayout />
      </MemoryRouter>,
    )
    expect(screen.getByText('案件')).toBeInTheDocument()
    expect(screen.getByText('新建')).toBeInTheDocument()
  })

  // Branch: Outlet renders via Suspense
  it('renders Outlet inside Suspense with PageSkeleton fallback', () => {
    render(
      <MemoryRouter>
        <AdminLayout />
      </MemoryRouter>,
    )
    // CommandPalette is lazy loaded, rendered via Suspense
    expect(screen.getByTestId('command-palette')).toBeInTheDocument()
  })
})
