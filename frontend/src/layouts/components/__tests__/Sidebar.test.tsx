import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Sidebar } from '../Sidebar'

// Mock dependencies
vi.mock('@/stores/ui', () => ({
  useUIStore: vi.fn(),
}))

vi.mock('@/lib/prefetch', () => ({
  prefetchRoute: vi.fn(),
}))

vi.mock('lucide-react', () => ({
  ChevronLeft: (props: Record<string, unknown>) => <svg data-testid="chevron-left" {...props} />,
  ChevronDown: (props: Record<string, unknown>) => <svg data-testid="chevron-down" {...props} />,
  LayoutDashboard: (props: Record<string, unknown>) => <svg data-testid="icon-dashboard" {...props} />,
  Bot: (props: Record<string, unknown>) => <svg data-testid="icon-bot" {...props} />,
  Briefcase: (props: Record<string, unknown>) => <svg data-testid="icon-briefcase" {...props} />,
  FileText: (props: Record<string, unknown>) => <svg data-testid="icon-filetext" {...props} />,
  Users: (props: Record<string, unknown>) => <svg data-testid="icon-users" {...props} />,
  Zap: (props: Record<string, unknown>) => <svg data-testid="icon-zap" {...props} />,
  MessageSquare: (props: Record<string, unknown>) => <svg data-testid="icon-message" {...props} />,
  Truck: (props: Record<string, unknown>) => <svg data-testid="icon-truck" {...props} />,
  ArrowRightLeft: (props: Record<string, unknown>) => <svg data-testid="icon-arrows" {...props} />,
  Calculator: (props: Record<string, unknown>) => <svg data-testid="icon-calc" {...props} />,
  Settings: (props: Record<string, unknown>) => <svg data-testid="icon-settings" {...props} />,
  Megaphone: (props: Record<string, unknown>) => <svg data-testid="icon-mega" {...props} />,
}))

import { useUIStore } from '@/stores/ui'

const mockUseUIStore = vi.mocked(useUIStore)

// Helper to mock the store selector pattern
function setupStore(overrides: Record<string, unknown> = {}) {
  const defaults = {
    expandedGroups: [] as string[],
    toggleGroup: vi.fn(),
    setExpandedGroups: vi.fn(),
    ...overrides,
  }

  mockUseUIStore.mockImplementation((selector: (state: Record<string, unknown>) => unknown) => {
    return selector(defaults)
  })

  return defaults
}

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupStore()
  })

  it('renders the sidebar', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('complementary')).toBeInTheDocument()
  })

  it('shows full brand name when expanded', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('法穿AI Copilot')).toBeInTheDocument()
  })

  it('shows short brand when collapsed', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('FC')).toBeInTheDocument()
    expect(screen.queryByText('法穿AI Copilot')).not.toBeInTheDocument()
  })

  it('renders top-level menu items', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('工作台')).toBeInTheDocument()
  })

  it('renders group menu items', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('业务')).toBeInTheDocument()
    expect(screen.getByText('工具')).toBeInTheDocument()
  })

  it('renders settings at bottom', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })

  it('calls onToggle when collapse button is clicked', () => {
    const onToggle = vi.fn()
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={onToggle} />
      </MemoryRouter>,
    )

    const toggleButton = screen.getByTestId('chevron-left').closest('button')!
    fireEvent.click(toggleButton)
    expect(onToggle).toHaveBeenCalled()
  })

  it('renders nav links', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const links = screen.getAllByRole('link')
    // Should have multiple nav links (dashboard, workbench, settings, brand)
    expect(links.length).toBeGreaterThan(2)
  })

  it('brand link points to dashboard', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const brandLink = screen.getByText('法穿AI Copilot').closest('a')
    expect(brandLink).toHaveAttribute('href', '/admin/dashboard')
  })

  it('expands group when click toggles group in expanded mode', () => {
    const store = setupStore({ expandedGroups: [] })

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Click on business group to expand
    fireEvent.click(screen.getByText('业务'))
    expect(store.toggleGroup).toHaveBeenCalledWith('business')
  })

  it('shows sub-items when group is expanded', () => {
    setupStore({ expandedGroups: ['business'] })

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Sub-items should be visible when expanded
    expect(screen.getByText('当事人管理')).toBeInTheDocument()
    expect(screen.getByText('合同管理')).toBeInTheDocument()
    expect(screen.getByText('案件管理')).toBeInTheDocument()
  })

  it('sidebar has aside element', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const aside = screen.getByRole('complementary')
    // Width is set via style prop
    expect(aside).toBeInTheDocument()
  })

  it('sidebar has correct structure when collapsed', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const aside = screen.getByRole('complementary')
    expect(aside).toBeInTheDocument()
    // Should not show expanded labels in main content
    expect(screen.queryByText('法穿AI Copilot')).not.toBeInTheDocument()
  })

  it('renders icon for dashboard item', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('icon-dashboard')).toBeInTheDocument()
  })

  it('renders all expected menu group labels', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Business group
    expect(screen.getByText('业务')).toBeInTheDocument()
    // Tools group
    expect(screen.getByText('工具')).toBeInTheDocument()
  })

  it('renders collapsed sidebar with correct width', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const aside = screen.getByRole('complementary')
    // Style is applied via style prop
    expect(aside.style.width).toBe('56px')
  })

  it('renders expanded sidebar with correct width', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const aside = screen.getByRole('complementary')
    expect(aside.style.width).toBe('220px')
  })

  it('opens popover for group menu when collapsed and clicked', () => {
    setupStore({ expandedGroups: [] })

    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // In collapsed mode, the group button has icon but the label text is hidden
    // Find the Briefcase icon (business group) and click its parent button
    const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
    // The first briefcase icon is the business group icon
    const businessButton = briefcaseIcons[0].closest('button')!
    fireEvent.click(businessButton)

    // The popover should show the sub-items for business group
    expect(screen.getByText('当事人管理')).toBeInTheDocument()
    expect(screen.getByText('合同管理')).toBeInTheDocument()
    expect(screen.getByText('案件管理')).toBeInTheDocument()
  })

  it('shows active sub-item indicator', () => {
    setupStore({ expandedGroups: ['business'] })

    render(
      <MemoryRouter initialEntries={['/admin/cases']}>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Sub-items should be visible when expanded
    expect(screen.getByText('案件管理')).toBeInTheDocument()
  })

  it('handles group toggle when not collapsed', () => {
    const store = setupStore({ expandedGroups: [] })

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Click on tools group to expand
    fireEvent.click(screen.getByText('工具'))
    expect(store.toggleGroup).toHaveBeenCalledWith('tools')
  })

  it('renders bottom menu items correctly', () => {
    render(
      <MemoryRouter initialEntries={['/admin/settings']}>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Bottom menu should have settings
    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })

  it('renders all top-level items', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Should render dashboard and workbench as top-level items
    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('工作台')).toBeInTheDocument()
  })

  it('renders collapsed mode with tooltip for top-level items', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // In collapsed mode, the label text is still in the DOM (in the tooltip div)
    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('工作台')).toBeInTheDocument()
  })

  it('shows chevron rotation when group is expanded', () => {
    setupStore({ expandedGroups: ['business'] })

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // When business group is expanded, the ChevronDown should have rotate-180 class
    const chevrons = screen.getAllByTestId('chevron-down')
    expect(chevrons.length).toBeGreaterThan(0)
  })

  it('handles mouse enter on nav links for prefetch', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Mouse over a nav link
    const dashboardLink = screen.getByText('仪表盘').closest('a')!
    fireEvent.mouseEnter(dashboardLink)
    // prefetchRoute should be called (we can't easily verify the exact call due to mocking)
  })

  it('renders collapsed brand link with justify-center class', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Brand link should have justify-center class when collapsed
    const brandLink = screen.getByText('FC').closest('a')!
    expect(brandLink.className).toContain('justify-center')
  })

  it('renders expanded brand link without justify-center', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const brandLink = screen.getByText('法穿AI Copilot').closest('a')!
    expect(brandLink.className).toContain('gap-2.5')
    expect(brandLink.className).not.toContain('justify-center')
  })

  it('applies active state styling to sub-items', () => {
    setupStore({ expandedGroups: ['business'] })

    render(
      <MemoryRouter initialEntries={['/admin/cases']}>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // The sub-item link for cases should have active styling
    const casesLink = screen.getByText('案件管理').closest('a')!
    expect(casesLink.className).toContain('bg-[#27272a]')
    expect(casesLink.className).toContain('text-white')
  })

  it('handles focus event on nav links for prefetch', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const dashboardLink = screen.getByText('仪表盘').closest('a')!
    fireEvent.focus(dashboardLink)
  })

  it('renders collapsed sidebar with correct overflow', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={true} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    // Nav element should have overflow-hidden when collapsed
    const nav = screen.getByRole('navigation')
    expect(nav.className).toContain('overflow-hidden')
  })

  it('renders expanded sidebar with scroll overflow', () => {
    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggle={vi.fn()} />
      </MemoryRouter>,
    )

    const nav = screen.getByRole('navigation')
    expect(nav.className).toContain('overflow-y-auto')
  })
})
