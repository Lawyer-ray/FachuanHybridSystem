import { useUIStore, selectSidebarCollapsed } from '../ui'

describe('useUIStore', () => {
  beforeEach(() => {
    // Reset to defaults
    useUIStore.setState({
      sidebarCollapsed: false,
      expandedGroups: ['business'],
    })
    localStorage.clear()
  })

  it('has correct initial state', () => {
    const state = useUIStore.getState()
    expect(state.sidebarCollapsed).toBe(false)
    expect(state.expandedGroups).toEqual(['business'])
  })

  it('toggleSidebar toggles collapsed state', () => {
    useUIStore.getState().toggleSidebar()
    expect(useUIStore.getState().sidebarCollapsed).toBe(true)
    useUIStore.getState().toggleSidebar()
    expect(useUIStore.getState().sidebarCollapsed).toBe(false)
  })

  it('setSidebarCollapsed sets collapsed state', () => {
    useUIStore.getState().setSidebarCollapsed(true)
    expect(useUIStore.getState().sidebarCollapsed).toBe(true)
    useUIStore.getState().setSidebarCollapsed(false)
    expect(useUIStore.getState().sidebarCollapsed).toBe(false)
  })

  it('toggleGroup adds group if not present', () => {
    useUIStore.getState().toggleGroup('admin')
    expect(useUIStore.getState().expandedGroups).toContain('admin')
    expect(useUIStore.getState().expandedGroups).toContain('business')
  })

  it('toggleGroup removes group if present', () => {
    useUIStore.getState().toggleGroup('business')
    expect(useUIStore.getState().expandedGroups).not.toContain('business')
  })

  it('setExpandedGroups replaces all groups', () => {
    useUIStore.getState().setExpandedGroups(['a', 'b', 'c'])
    expect(useUIStore.getState().expandedGroups).toEqual(['a', 'b', 'c'])
  })
})

describe('selectSidebarCollapsed', () => {
  it('returns sidebarCollapsed value', () => {
    expect(selectSidebarCollapsed({ sidebarCollapsed: true } as any)).toBe(true)
    expect(selectSidebarCollapsed({ sidebarCollapsed: false } as any)).toBe(false)
  })
})
