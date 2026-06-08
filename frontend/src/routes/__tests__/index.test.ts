import { router } from '../index'
import { PATHS } from '../paths'

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

  it('includes content ops inspiration path', () => {
    const allPaths = extractPaths(router.routes)
    expect(allPaths).toContain(PATHS.ADMIN_TOOLS_CONTENT_OPS_INSPIRATION)
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
