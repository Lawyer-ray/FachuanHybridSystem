import { router } from '../index'

describe('router configuration', () => {
  it('exports a router instance', () => {
    expect(router).toBeDefined()
  })

  it('has routes configured', () => {
    const routes = router.routes
    expect(routes.length).toBeGreaterThan(0)
  })

  it('has a root redirect route', () => {
    const rootRoute = router.routes.find((r) => r.path === '/')
    expect(rootRoute).toBeDefined()
  })

  it('has a catch-all route', () => {
    const catchAllRoute = router.routes.find((r) => r.path === '*')
    expect(catchAllRoute).toBeDefined()
  })

  it('has guest guard for auth pages', () => {
    // GuestGuard is the element of one of the top-level routes
    // and it contains auth pages as children
    const guestRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/login')),
    )
    expect(guestRoute).toBeDefined()
  })

  it('has auth guard for admin pages', () => {
    // AuthGuard wraps admin routes
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    expect(adminRoute).toBeDefined()
  })

  it('includes all expected auth paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/login')
    expect(allPaths).toContain('/register')
    expect(allPaths).toContain('/forgot-password')
    expect(allPaths).toContain('/reset-password')
  })

  it('includes all expected admin paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/admin/dashboard')
    expect(allPaths).toContain('/admin/clients')
    expect(allPaths).toContain('/admin/cases')
    expect(allPaths).toContain('/admin/contracts')
    expect(allPaths).toContain('/admin/inbox')
    expect(allPaths).toContain('/admin/settings')
    expect(allPaths).toContain('/admin/automation')
  })

  it('includes automation tool paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/admin/automation/preservation-quotes')
    expect(allPaths).toContain('/admin/automation/document-recognition')
  })

  it('includes tool paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/admin/tools/court-sms')
    expect(allPaths).toContain('/admin/tools/courier-tracking')
    expect(allPaths).toContain('/admin/tools/element-convert')
    expect(allPaths).toContain('/admin/tools/lpr-calculator')
    expect(allPaths).toContain('/admin/tools/content-ops')
  })

  it('includes organization paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/admin/organization')
    expect(allPaths).toContain('/admin/organization/lawfirms/new')
    expect(allPaths).toContain('/admin/organization/lawyers/new')
  })

  it('includes settings paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain('/admin/settings/law-firm')
    expect(allPaths).toContain('/admin/settings/team')
    expect(allPaths).toContain('/admin/settings/lawyer')
  })

  it('has a catch-all 404 route under admin layout', () => {
    const allPaths = extractPaths(router.routes)
    // The wildcard * route for 404
    expect(allPaths).toContain('*')
  })
})

/** Recursively extract all route paths from the route tree */
function extractPaths(routes: Array<Record<string, unknown>>): string[] {
  const paths: string[] = []
  for (const route of routes) {
    if (typeof route.path === 'string') {
      paths.push(route.path)
    }
    if (Array.isArray(route.children)) {
      paths.push(...extractPaths(route.children as Array<Record<string, unknown>>))
    }
  }
  return paths
}
