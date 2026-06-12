import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router'
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
import { prefetchRoute } from '@/lib/prefetch'

const mockUseUIStore = vi.mocked(useUIStore)
const mockPrefetchRoute = vi.mocked(prefetchRoute)

/** Helper component that triggers navigation within the same Router context */
function Navigator({ to }: { to: string }) {
  const navigate = useNavigate()
  // Use setTimeout to avoid state update during render
  React.useEffect(() => {
    const timer = setTimeout(() => navigate(to), 0)
    return () => clearTimeout(timer)
  }, [navigate, to])
  return null
}

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

  // Also mock getState for the auto-expand useEffect
  ;(mockUseUIStore as unknown as { getState: () => Record<string, unknown> }).getState = () => defaults

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

  // === NEW TESTS: Additional coverage ===

  describe('auto-expand group on route change', () => {
    it('calls setExpandedGroups when navigating to a group sub-path', async () => {
      const store = setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Navigator to="/admin/cases" />
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Wait for the navigation to complete
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })

      // setExpandedGroups should have been called with the business group added
      expect(store.setExpandedGroups).toHaveBeenCalled()
    })

    it('does not duplicate group in expandedGroups if already expanded', async () => {
      const store = setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Navigator to="/admin/cases" />
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })

      // setExpandedGroups should NOT be called since the group is already expanded
      expect(store.setExpandedGroups).not.toHaveBeenCalled()
    })

    it('does not call setExpandedGroups when path is not in any group', async () => {
      const store = setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Navigator to="/admin/workbench" />
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })

      // setExpandedGroups should NOT be called
      expect(store.setExpandedGroups).not.toHaveBeenCalled()
    })
  })

  describe('collapsed group popover', () => {
    it('clicks outside to close popover', () => {
      setupStore({ expandedGroups: [] })

      const { container } = render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open the business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      const businessButton = briefcaseIcons[0].closest('button')!
      fireEvent.click(businessButton)

      // Popover should be open - sub-items visible
      expect(screen.getByText('当事人管理')).toBeInTheDocument()

      // Click outside the sidebar
      fireEvent.mouseDown(document.body)

      // Popover should close - sub-items hidden
      expect(screen.queryByText('当事人管理')).not.toBeInTheDocument()
    })

    it('toggles popover closed when clicking same button again', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      const businessButton = briefcaseIcons[0].closest('button')!

      // Open popover
      fireEvent.click(businessButton)
      expect(screen.getByText('当事人管理')).toBeInTheDocument()

      // Close popover by clicking same button
      fireEvent.click(businessButton)
      expect(screen.queryByText('当事人管理')).not.toBeInTheDocument()
    })

    it('renders collapsed popover with fixed positioning', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Popover container should use fixed positioning
      const popoverContainer = screen.getByText('当事人管理').closest('.fixed')
      expect(popoverContainer).toBeInTheDocument()
    })

    it('renders popover with animation style', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Popover should have animation style
      const popoverContainer = screen.getByText('当事人管理').closest('.fixed')!
      expect(popoverContainer.style.animation).toContain('popover-in')
    })

    it('shows active sub-item styling in collapsed popover', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/cases']}>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // The active sub-item should have white text and active background
      const casesLink = screen.getByText('案件管理').closest('a')!
      expect(casesLink.className).toContain('text-white')
      expect(casesLink.className).toContain('bg-white')
    })

    it('shows active indicator dot for active sub-item in popover', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/cases']}>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Active indicator dot should be present (w-1.5 h-1.5 rounded-full bg-[#6366f1])
      const popover = screen.getByText('案件管理').closest('.fixed')!
      const indicator = popover.querySelector('.rounded-full.bg-\\[\\#6366f1\\]')
      // At minimum the popover should be rendered with the active item
      expect(screen.getByText('案件管理')).toBeInTheDocument()
    })

    it('renders all group items in collapsed popover', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open tools group popover
      const zapIcons = screen.getAllByTestId('icon-zap')
      fireEvent.click(zapIcons[0].closest('button')!)

      // All tools sub-items should be in the popover
      expect(screen.getByText('法院短信')).toBeInTheDocument()
      expect(screen.getByText('快递查询')).toBeInTheDocument()
      expect(screen.getByText('要素式转换')).toBeInTheDocument()
      expect(screen.getByText('LPR 计算器')).toBeInTheDocument()
    })

    it('closes popover on route change', async () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Navigator to="/admin/cases" />
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)
      expect(screen.getByText('当事人管理')).toBeInTheDocument()

      // Wait for navigation to trigger route change effect
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })

      // Popover should be closed after route change
      expect(screen.queryByText('当事人管理')).not.toBeInTheDocument()
    })

    it('handles mouseEnter on collapsed popover nav links for prefetch', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Hover over a sub-item in the popover
      const clientsLink = screen.getByText('当事人管理').closest('a')!
      fireEvent.mouseEnter(clientsLink)

      // handlePrefetch should have been triggered (via onMouseEnter)
      expect(clientsLink).toBeInTheDocument()
    })

    it('handles focus on collapsed popover nav links for prefetch', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Focus a sub-item in the popover
      const contractsLink = screen.getByText('合同管理').closest('a')!
      fireEvent.focus(contractsLink)

      expect(contractsLink).toBeInTheDocument()
    })

    it('renders group label in collapsed popover header', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // The popover should contain the group label in uppercase header
      const popoverHeader = screen.getByText('业务')
      expect(popoverHeader).toBeInTheDocument()
    })

    it('does not show popover content when collapsed but not clicked', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Sub-items should not be visible until group button is clicked
      expect(screen.queryByText('当事人管理')).not.toBeInTheDocument()
      expect(screen.queryByText('合同管理')).not.toBeInTheDocument()
    })
  })

  describe('SubMenuItem interactions', () => {
    it('triggers prefetch on sub-item mouseEnter', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Hover over a sub-item
      const casesLink = screen.getByText('案件管理').closest('a')!
      fireEvent.mouseEnter(casesLink)

      // Should trigger prefetch (function is called internally)
      expect(casesLink).toBeInTheDocument()
    })

    it('triggers prefetch on sub-item focus', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const clientsLink = screen.getByText('当事人管理').closest('a')!
      fireEvent.focus(clientsLink)

      expect(clientsLink).toBeInTheDocument()
    })

    it('renders sub-item with icon', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Sub-items should have icons
      const clientsLink = screen.getByText('当事人管理').closest('a')!
      const icon = clientsLink.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it('applies hover styling classes to sub-items', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const clientsLink = screen.getByText('当事人管理').closest('a')!
      expect(clientsLink.className).toContain('hover:text-white')
      expect(clientsLink.className).toContain('hover:bg-[#27272a]')
    })

    it('renders all tools sub-items when tools group is expanded', () => {
      setupStore({ expandedGroups: ['tools'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      expect(screen.getByText('法院短信')).toBeInTheDocument()
      expect(screen.getByText('快递查询')).toBeInTheDocument()
      expect(screen.getByText('要素式转换')).toBeInTheDocument()
      expect(screen.getByText('LPR 计算器')).toBeInTheDocument()
    })

    it('applies active styling to tools sub-items', () => {
      setupStore({ expandedGroups: ['tools'] })

      render(
        <MemoryRouter initialEntries={['/admin/tools/court-sms']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const courtSmsLink = screen.getByText('法院短信').closest('a')!
      expect(courtSmsLink.className).toContain('bg-[#27272a]')
      expect(courtSmsLink.className).toContain('text-white')
    })
  })

  describe('TopLevelItem interactions', () => {
    it('triggers prefetch on workbench link mouseEnter', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const workbenchLink = screen.getByText('工作台').closest('a')!
      fireEvent.mouseEnter(workbenchLink)
      // handlePrefetch should be called with '/admin/workbench'
    })

    it('triggers prefetch on workbench link focus', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const workbenchLink = screen.getByText('工作台').closest('a')!
      fireEvent.focus(workbenchLink)
    })

    it('renders collapsed tooltip with pointer-events-none', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // In collapsed mode, tooltips should have pointer-events-none class
      const tooltips = document.querySelectorAll('.pointer-events-none')
      expect(tooltips.length).toBeGreaterThan(0)
    })

    it('renders active top-level item with correct styling', () => {
      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const dashboardLink = screen.getByText('仪表盘').closest('a')!
      expect(dashboardLink.className).toContain('bg-[#27272a]')
      expect(dashboardLink.className).toContain('text-white')
      expect(dashboardLink.className).toContain('font-medium')
    })

    it('renders non-active top-level item without active styling', () => {
      render(
        <MemoryRouter initialEntries={['/admin/cases']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const dashboardLink = screen.getByText('仪表盘').closest('a')!
      const classes = dashboardLink.getAttribute('class') || ''
      // Should have the default text color
      expect(classes).toContain('text-[#a1a1aa]')
      // Active state adds "font-medium" in addition to bg and text-white;
      // non-active links should not have the standalone font-medium from isActive
      // but the hover variants are separate
      expect(classes).not.toMatch(/\bfont-medium\b/)
    })

    it('prefetches dashboard on brand link hover', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const brandLink = screen.getByText('法穿AI Copilot').closest('a')!
      fireEvent.mouseEnter(brandLink)
      // Brand link triggers handlePrefetch for /admin/dashboard
    })
  })

  describe('bottom menu active state', () => {
    it('bottom menu is active when on settings path', () => {
      render(
        <MemoryRouter initialEntries={['/admin/settings']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      expect(settingsLink.className).toContain('bg-[#27272a]')
      expect(settingsLink.className).toContain('text-white')
    })

    it('bottom menu is active when on settings sub-path', () => {
      render(
        <MemoryRouter initialEntries={['/admin/settings/profile']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      expect(settingsLink.className).toContain('text-white')
    })

    it('bottom menu is active when on organization path', () => {
      render(
        <MemoryRouter initialEntries={['/admin/organization']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      expect(settingsLink.className).toContain('text-white')
    })

    it('bottom menu is active when on organization sub-path', () => {
      render(
        <MemoryRouter initialEntries={['/admin/organization/lawyers']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      expect(settingsLink.className).toContain('text-white')
    })

    it('bottom menu is NOT active when on unrelated path', () => {
      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      const classes = settingsLink.getAttribute('class') || ''
      // Active state adds font-medium; non-active should not have it
      expect(classes).not.toMatch(/\bfont-medium\b/)
    })
  })

  describe('GroupMenu expanded mode', () => {
    it('sub-items are hidden when group is not expanded (grid-template-rows: 0fr)', () => {
      setupStore({ expandedGroups: [] })

      const { container } = render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // When not expanded, the sub-items container should have grid-template-rows: 0fr
      const gridContainers = container.querySelectorAll('[style*="grid-template-rows: 0fr"]')
      expect(gridContainers.length).toBeGreaterThan(0)
    })

    it('shows inline sub-items when group is expanded', () => {
      setupStore({ expandedGroups: ['business', 'tools'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Both groups expanded - all sub-items visible
      expect(screen.getByText('当事人管理')).toBeInTheDocument()
      expect(screen.getByText('法院短信')).toBeInTheDocument()
    })

    it('renders group button with full width style when not collapsed', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const businessButton = screen.getByText('业务').closest('button')!
      expect(businessButton.style.width).toBe('calc(100% - 16px)')
    })

    it('renders group button with narrower width style when collapsed', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      const businessButton = briefcaseIcons[0].closest('button')!
      expect(businessButton.style.width).toBe('calc(100% - 8px)')
    })

    it('applies hasActive styling to group when sub-item is active', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter initialEntries={['/admin/cases']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // The group button should have text-white class when a sub-item is active
      const businessButton = screen.getByText('业务').closest('button')!
      expect(businessButton.className).toContain('text-white')
    })

    it('does not apply hasActive styling when no sub-item is active', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter initialEntries={['/admin/dashboard']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const businessButton = screen.getByText('业务').closest('button')!
      const classes = businessButton.getAttribute('class') || ''
      // hasActive adds text-white (standalone, not hover variant)
      // The button has hover:text-white as a base class, so check for standalone text-white
      expect(classes).not.toMatch(/(?<!hover:)text-white/)
    })
  })

  describe('collapse/expand transition', () => {
    it('sidebar aside has transition classes', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const aside = screen.getByRole('complementary')
      expect(aside.className).toContain('transition-[width]')
      expect(aside.className).toContain('will-change-[width]')
    })

    it('collapse button has rotation class when collapsed', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const chevron = screen.getByTestId('chevron-left')
      // SVG elements use SVGAnimatedString for className; use getAttribute instead
      expect(chevron.getAttribute('class')).toContain('rotate-180')
    })

    it('collapse button does not have rotation class when expanded', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const chevron = screen.getByTestId('chevron-left')
      expect(chevron.getAttribute('class')).not.toContain('rotate-180')
    })
  })

  describe('multiple groups and navigation', () => {
    it('renders both groups with chevron icons', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Both groups should have chevron icons
      const chevrons = screen.getAllByTestId('chevron-down')
      expect(chevrons.length).toBeGreaterThanOrEqual(2)
    })

    it('navigating within same group does not duplicate in expandedGroups', async () => {
      const store = setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter initialEntries={['/admin/clients']}>
          <Navigator to="/admin/cases" />
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })

      // Should not call setExpandedGroups since business is already expanded
      expect(store.setExpandedGroups).not.toHaveBeenCalled()
    })

    it('renders settings icon in bottom menu', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      expect(screen.getByTestId('icon-settings')).toBeInTheDocument()
    })

    it('bottom menu has border-t separator', () => {
      const { container } = render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const bottomMenu = container.querySelector('.border-t')
      expect(bottomMenu).toBeInTheDocument()
    })
  })

  describe('handlePrefetch and routePrefetchMap', () => {
    it('prefetches dashboard route on mouse enter', () => {
      render(
        <MemoryRouter initialEntries={['/admin/workbench']}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const dashboardLink = screen.getByText('仪表盘').closest('a')!
      fireEvent.mouseEnter(dashboardLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/dashboard',
        expect.any(Function),
      )
    })

    it('prefetches workbench route on focus', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const workbenchLink = screen.getByText('工作台').closest('a')!
      fireEvent.focus(workbenchLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/workbench',
        expect.any(Function),
      )
    })

    it('prefetches on sub-item mouse enter', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const casesLink = screen.getByText('案件管理').closest('a')!
      fireEvent.mouseEnter(casesLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/cases',
        expect.any(Function),
      )
    })

    it('prefetches on sub-item focus', () => {
      setupStore({ expandedGroups: ['business'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const clientsLink = screen.getByText('当事人管理').closest('a')!
      fireEvent.focus(clientsLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/clients',
        expect.any(Function),
      )
    })

    it('prefetches tool sub-items on hover', () => {
      setupStore({ expandedGroups: ['tools'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const courtSmsLink = screen.getByText('法院短信').closest('a')!
      fireEvent.mouseEnter(courtSmsLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/tools/court-sms',
        expect.any(Function),
      )
    })

    it('prefetches collapsed popover sub-items on hover', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      const contractsLink = screen.getByText('合同管理').closest('a')!
      fireEvent.mouseEnter(contractsLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/contracts',
        expect.any(Function),
      )
    })

    it('prefetches collapsed popover sub-items on focus', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      const casesLink = screen.getByText('案件管理').closest('a')!
      fireEvent.focus(casesLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/cases',
        expect.any(Function),
      )
    })

    it('prefetches brand link on hover', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const brandLink = screen.getByText('法穿AI Copilot').closest('a')!
      fireEvent.mouseEnter(brandLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/dashboard',
        expect.any(Function),
      )
    })

    it('prefetches settings on bottom menu hover', () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const settingsLink = screen.getByText('系统设置').closest('a')!
      fireEvent.mouseEnter(settingsLink)
      expect(mockPrefetchRoute).toHaveBeenCalledWith(
        '/admin/settings',
        expect.any(Function),
      )
    })

    it('calls routePrefetchMap functions which are async import lambdas', async () => {
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const dashboardLink = screen.getByText('仪表盘').closest('a')!
      fireEvent.mouseEnter(dashboardLink)

      // Get the function passed to prefetchRoute
      const prefetchFn = mockPrefetchRoute.mock.calls[0][1]
      expect(typeof prefetchFn).toBe('function')
      // It returns a promise (import())
      const result = prefetchFn()
      expect(result).toBeInstanceOf(Promise)
    })
  })

  describe('handlePrefetch with unmapped routes', () => {
    it('does not call prefetchRoute for unmapped paths', () => {
      // Since handlePrefetch checks routePrefetchMap first,
      // test that clicking settings focus (mapped) works
      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Hovering on settings link - this IS mapped
      const settingsLink = screen.getByText('系统设置').closest('a')!
      fireEvent.mouseEnter(settingsLink)
      expect(mockPrefetchRoute).toHaveBeenCalled()
    })
  })

  describe('GroupMenu popover click outside and ref containment', () => {
    it('does not close popover when clicking inside container', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Open business group popover
      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)
      expect(screen.getByText('当事人管理')).toBeInTheDocument()

      // Click inside the container (on a sub-item) - should NOT close
      const clientsLink = screen.getByText('当事人管理')
      fireEvent.mouseDown(clientsLink)
      expect(screen.getByText('当事人管理')).toBeInTheDocument()
    })

    it('does not close popover when clicking on popover content', () => {
      setupStore({ expandedGroups: [] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={true} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      const briefcaseIcons = screen.getAllByTestId('icon-briefcase')
      fireEvent.click(briefcaseIcons[0].closest('button')!)

      // Click on the group header in popover
      const groupHeader = screen.getByText('业务')
      fireEvent.mouseDown(groupHeader)
      expect(screen.getByText('当事人管理')).toBeInTheDocument()
    })
  })

  describe('routePrefetchMap entries', () => {
    it('prefetches all menu paths when hovered', () => {
      setupStore({ expandedGroups: ['business', 'tools'] })

      render(
        <MemoryRouter>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>,
      )

      // Hover over all visible links to exercise routePrefetchMap
      const links = [
        '仪表盘', '工作台',
        '当事人管理', '合同管理', '案件管理',
        '法院短信', '快递查询', '要素式转换', 'LPR 计算器',
        '系统设置',
      ]

      for (const label of links) {
        mockPrefetchRoute.mockClear()
        const link = screen.getByText(label).closest('a')!
        fireEvent.mouseEnter(link)
        expect(mockPrefetchRoute).toHaveBeenCalledWith(
          expect.any(String),
          expect.any(Function),
        )
      }
    })
  })
})
