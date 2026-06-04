import { useEffect, useState, useCallback, useMemo, useRef, lazy, Suspense } from 'react'
import { Outlet, useLocation } from 'react-router'
import { useUIStore } from '@/stores/ui'
import { Sidebar } from './components/Sidebar'
import { Navbar } from './components/Navbar'
import { Breadcrumb, type BreadcrumbItem } from './components/Breadcrumb'
import { PATHS } from '@/routes/paths'
import {
  BreadcrumbProvider,
  useBreadcrumbContext,
} from '@/contexts/BreadcrumbContext'
import { PageSkeleton } from '@/components/shared/PageSkeleton'

const CommandPalette = lazy(() =>
  import('@/components/shared/CommandPalette').then((m) => ({ default: m.CommandPalette }))
)

const MOBILE_BREAKPOINT = 768
const CURRENT_YEAR = new Date().getFullYear()

/** 不可独立访问的路径段（仅作为路由前缀，无对应 index 页面） */
const NO_LINK_SEGMENTS = new Set(['config'])

/** 路径段 → 中文标签映射 */
const ROUTE_LABELS: Record<string, string> = {
  cases: '案件', contracts: '合同', clients: '当事人', documents: '文书',
  settings: '设置', automation: '自动化工具', 'preservation-quotes': '财产保全询价',
  'document-recognition': '文书智能识别', new: '新建', edit: '编辑',
  user: '用户设置', system: '系统配置', tools: '工具', 'law-firm': '律所设置',
  team: '团队设置', lawyer: '律师设置', config: '服务配置',
  templates: '文件模板', inbox: '收件箱', 'message-sources': '消息来源',
  'task-queue': '任务队列', logs: '日志',
  'court-sms': '法院短信', 'courier-tracking': '快递查询',
  'element-convert': '要素式转换', 'lpr-calculator': 'LPR 计算器',
  'content-ops': '内容运营', inspiration: '选题灵感',
  ai: 'AI', email: '邮件', sms: '短信', storage: '存储', llm: 'LLM',
}

function generateBreadcrumbItems(pathname: string): BreadcrumbItem[] {
  const items: BreadcrumbItem[] = [
    { label: '首页', path: PATHS.ADMIN_DASHBOARD },
  ]

  const segments = pathname.split('/').filter(Boolean)
  if (segments[0] === 'admin') segments.shift()
  if (segments.length === 0 || segments[0] === 'dashboard') return [{ label: '首页' }]

  let currentPath = '/admin'
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i]
    const isLast = i === segments.length - 1
    if (/^\d+$/.test(segment) || /^[a-f0-9-]{36}$/i.test(segment)) continue

    const label = ROUTE_LABELS[segment] || segment
    currentPath += `/${segment}`

    // 无独立页面的路径段：仅显示标签，不生成链接
    if (NO_LINK_SEGMENTS.has(segment)) {
      items.push({ label })
      continue
    }

    items.push(isLast ? { label } : { label, path: currentPath })
  }

  return items
}

function AdminLayoutContent() {
  const location = useLocation()
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed)
  const toggleSidebar = useUIStore((state) => state.toggleSidebar)
  const setSidebarCollapsed = useUIStore((state) => state.setSidebarCollapsed)
  const { customItems } = useBreadcrumbContext()

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [showFooter, setShowFooter] = useState(false)
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      if (mobile && !sidebarCollapsed) setSidebarCollapsed(true)
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [setSidebarCollapsed, sidebarCollapsed])

  useEffect(() => { setMobileMenuOpen(false) }, [location.pathname])

  const handleMobileMenuClick = useCallback(() => setMobileMenuOpen(true), [])
  const closeMobileMenu = useCallback(() => setMobileMenuOpen(false), [])

  const breadcrumbItems = useMemo(
    () => customItems ?? generateBreadcrumbItems(location.pathname),
    [customItems, location.pathname],
  )
  const mainMarginLeft = isMobile ? 0 : sidebarCollapsed ? 56 : 220
  const isWorkbench = location.pathname.startsWith(PATHS.ADMIN_WORKBENCH)

  // 自适应 footer：内容不满屏时才显示
  const FOOTER_THRESHOLD = 80
  useEffect(() => {
    const el = mainRef.current
    if (!el || isWorkbench) { setShowFooter(false); return }

    const observer = new ResizeObserver(() => {
      const contentH = el.scrollHeight
      const available = window.innerHeight - contentH
      setShowFooter(available > FOOTER_THRESHOLD)
    })
    observer.observe(el)
    const available = window.innerHeight - el.scrollHeight
    setShowFooter(available > FOOTER_THRESHOLD)
    return () => observer.disconnect()
  }, [location.pathname, isWorkbench])

  return (
    <div className="bg-background relative min-h-screen">
      <Suspense fallback={null}>
        <CommandPalette />
      </Suspense>

      {/* 桌面端 Sidebar */}
      {!isMobile && (
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
      )}

      {/* 移动端遮罩 + Sidebar 抽屉 */}
      {isMobile && mobileMenuOpen && (
        <>
          <div
            role="presentation"
            className="fixed inset-0 z-40 bg-black/50 transition-opacity duration-200"
            onClick={closeMobileMenu}
            onKeyDown={(e) => { if (e.key === 'Escape') closeMobileMenu() }}
            tabIndex={-1}
          />
          <div className="fixed left-0 top-0 z-50 h-full w-[260px]">
            <Sidebar collapsed={false} onToggle={closeMobileMenu} />
          </div>
        </>
      )}

      {/* 主内容区域 */}
      <div
        className="relative z-10 flex min-h-screen flex-col transition-[margin-left] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] will-change-[margin-left]"
        style={{ marginLeft: mainMarginLeft }}
      >
        <Navbar onMenuClick={handleMobileMenuClick} />

        <main ref={mainRef} className={`flex-1 px-6 pt-4 pb-0 ${isWorkbench ? 'overflow-hidden' : ''}`}>
          <div className="mb-4">
            <Breadcrumb items={breadcrumbItems} />
          </div>
          <Suspense fallback={<PageSkeleton />}>
            <Outlet />
          </Suspense>
        </main>

        {showFooter && (
          <footer className="border-border border-t px-6 py-3">
            <p className="text-muted-foreground text-center text-xs">
              © {CURRENT_YEAR} 法穿AI Copilot
            </p>
          </footer>
        )}
      </div>
    </div>
  )
}

export function AdminLayout() {
  return (
    <BreadcrumbProvider>
      <AdminLayoutContent />
    </BreadcrumbProvider>
  )
}

export default AdminLayout
