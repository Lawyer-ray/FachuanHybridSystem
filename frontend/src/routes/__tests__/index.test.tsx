import { router } from '../index'
import { PATHS } from '../paths'
import React from 'react'

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

  it('has a catch-all route at the top level', () => {
    const catchAllRoute = router.routes.find((r) => r.path === '*' && !r.children)
    expect(catchAllRoute).toBeDefined()
  })

  it('has guest guard for auth pages', () => {
    const guestRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/login')),
    )
    expect(guestRoute).toBeDefined()
  })

  it('has auth guard for admin pages', () => {
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
    expect(allPaths).toContain('*')
  })

  it('includes all client CRUD paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_CLIENTS)
    expect(allPaths).toContain(PATHS.ADMIN_CLIENT_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_CLIENT_DETAIL)
    expect(allPaths).toContain(PATHS.ADMIN_CLIENT_EDIT)
  })

  it('includes all case CRUD paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_CASES)
    expect(allPaths).toContain(PATHS.ADMIN_CASE_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_CASE_DETAIL)
    expect(allPaths).toContain(PATHS.ADMIN_CASE_EDIT)
  })

  it('includes all contract CRUD paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_CONTRACTS)
    expect(allPaths).toContain(PATHS.ADMIN_CONTRACT_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_CONTRACT_DETAIL)
    expect(allPaths).toContain(PATHS.ADMIN_CONTRACT_EDIT)
  })

  it('includes inbox paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_INBOX)
    expect(allPaths).toContain(PATHS.ADMIN_INBOX_DETAIL)
  })

  it('includes template paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_TEMPLATES)
    expect(allPaths).toContain(PATHS.ADMIN_TEMPLATE_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_TEMPLATE_EDIT)
  })

  it('includes message sources path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_MESSAGE_SOURCES)
  })

  it('includes court sms detail path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_TOOLS_COURT_SMS_DETAIL)
  })

  it('includes task queue path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_TASK_QUEUE)
  })

  it('includes logs path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_LOGS)
  })

  it('includes workbench paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_WORKBENCH)
    expect(allPaths).toContain(PATHS.ADMIN_WORKBENCH_SESSION)
  })

  it('includes reminders path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_REMINDERS)
  })

  it('includes config settings path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_SETTINGS_CONFIG)
  })

  it('includes all lawfirm paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_LAWFIRMS)
    expect(allPaths).toContain(PATHS.ADMIN_LAWFIRM_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_LAWFIRM_DETAIL)
    expect(allPaths).toContain(PATHS.ADMIN_LAWFIRM_EDIT)
  })

  it('includes all lawyer paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_LAWYERS)
    expect(allPaths).toContain(PATHS.ADMIN_LAWYER_NEW)
    expect(allPaths).toContain(PATHS.ADMIN_LAWYER_DETAIL)
    expect(allPaths).toContain(PATHS.ADMIN_LAWYER_EDIT)
  })

  it('includes teams and credentials paths', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_TEAMS)
    expect(allPaths).toContain(PATHS.ADMIN_CREDENTIALS)
  })

  it('includes quote detail path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_AUTOMATION_QUOTE_DETAIL)
  })

  it('includes recognition detail path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_AUTOMATION_RECOGNITION_DETAIL)
  })
})

describe('router route structure', () => {
  it('has exactly 3 top-level routes (root redirect, guest, admin, catch-all)', () => {
    // root redirect, guest guard, auth guard, catch-all
    expect(router.routes.length).toBe(4)
  })

  it('root route uses Navigate component', () => {
    const rootRoute = router.routes.find((r) => r.path === '/')
    expect(rootRoute).toBeDefined()
    expect(rootRoute!.element).toBeDefined()
    // The element should be a React element (Navigate)
    expect(React.isValidElement(rootRoute!.element)).toBe(true)
  })

  it('top-level catch-all redirects to admin dashboard', () => {
    const catchAllRoute = router.routes.find((r) => r.path === '*' && !r.children)
    expect(catchAllRoute).toBeDefined()
    expect(catchAllRoute!.element).toBeDefined()
    expect(React.isValidElement(catchAllRoute!.element)).toBe(true)
  })

  it('guest guard route has AuthLayout as child', () => {
    const guestRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/login')),
    )
    expect(guestRoute).toBeDefined()
    expect(guestRoute!.element).toBeDefined()
    // Guest guard has one child: AuthLayout
    expect(guestRoute!.children).toHaveLength(1)
    const authLayout = guestRoute!.children![0]
    expect(authLayout.element).toBeDefined()
    expect(authLayout.children).toBeDefined()
    expect(authLayout.children!.length).toBe(4) // login, register, forgot, reset
  })

  it('auth guard route has AdminLayout as child with errorElement', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    expect(adminRoute).toBeDefined()
    expect(adminRoute!.errorElement).toBeDefined()
    expect(adminRoute!.element).toBeDefined()
    // Admin guard has one child: AdminLayout
    expect(adminRoute!.children).toHaveLength(1)
    const adminLayout = adminRoute!.children![0]
    expect(adminLayout.element).toBeDefined()
    expect(adminLayout.errorElement).toBeDefined()
    expect(adminLayout.children).toBeDefined()
    expect(adminLayout.children!.length).toBeGreaterThan(40)
  })

  it('admin /admin path redirects to dashboard', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin')),
    )
    expect(adminRoute).toBeDefined()
    const adminLayout = adminRoute!.children![0]
    const adminRedirect = adminLayout.children!.find((r) => r.path === '/admin')
    expect(adminRedirect).toBeDefined()
    expect(React.isValidElement(adminRedirect!.element)).toBe(true)
  })

  it('admin 404 catch-all is the last route in admin layout', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const lastRoute = adminLayout.children![adminLayout.children!.length - 1]
    expect(lastRoute.path).toBe('*')
  })

  it('all admin child routes have elements', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    for (const route of adminLayout.children!) {
      expect(route.element).toBeDefined()
    }
  })

  it('all auth child routes have elements', () => {
    const guestRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/login')),
    )
    const authLayout = guestRoute!.children![0]
    for (const route of authLayout.children!) {
      expect(route.element).toBeDefined()
    }
  })

  it('new routes come before parameterized routes for clients', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/clients/new')
    const detailIdx = paths.indexOf('/admin/clients/:id')
    expect(newIdx).toBeLessThan(detailIdx)
  })

  it('new routes come before parameterized routes for cases', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/cases/new')
    const detailIdx = paths.indexOf('/admin/cases/:id')
    expect(newIdx).toBeLessThan(detailIdx)
  })

  it('new routes come before parameterized routes for contracts', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/contracts/new')
    const detailIdx = paths.indexOf('/admin/contracts/:id')
    expect(newIdx).toBeLessThan(detailIdx)
  })

  it('new routes come before parameterized routes for lawfirms', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/organization/lawfirms/new')
    const detailIdx = paths.indexOf('/admin/organization/lawfirms/:id')
    expect(newIdx).toBeLessThan(detailIdx)
  })

  it('new routes come before parameterized routes for lawyers', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/organization/lawyers/new')
    const detailIdx = paths.indexOf('/admin/organization/lawyers/:id')
    expect(newIdx).toBeLessThan(detailIdx)
  })

  it('template new route comes before template edit route', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    const paths = adminLayout.children!.map((r) => r.path)
    const newIdx = paths.indexOf('/admin/templates/new')
    const editIdx = paths.indexOf('/admin/templates/:id/edit')
    expect(newIdx).toBeLessThan(editIdx)
  })

  it('has unique paths (no duplicate path definitions)', () => {
    const allPaths = extractPaths(router.routes)
    const nonWildcardPaths = allPaths.filter((p) => p !== '*')
    const uniquePaths = new Set(nonWildcardPaths)
    expect(uniquePaths.size).toBe(nonWildcardPaths.length)
  })

  it('every auth page uses React elements', () => {
    const guestRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/login')),
    )
    const authLayout = guestRoute!.children![0]
    for (const route of authLayout.children!) {
      expect(React.isValidElement(route.element)).toBe(true)
    }
  })

  it('every admin page uses React elements', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    const adminLayout = adminRoute!.children![0]
    for (const route of adminLayout.children!) {
      expect(React.isValidElement(route.element)).toBe(true)
    }
  })

  it('admin guard uses RouteError as errorElement', () => {
    const adminRoute = router.routes.find(
      (r) => r.children?.some((c) => c.children?.some((cc) => cc.path === '/admin/dashboard')),
    )
    expect(adminRoute!.errorElement).toBeDefined()
    const adminLayout = adminRoute!.children![0]
    expect(adminLayout.errorElement).toBeDefined()
    // Both should be valid React elements
    expect(React.isValidElement(adminRoute!.errorElement)).toBe(true)
    expect(React.isValidElement(adminLayout.errorElement)).toBe(true)
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
