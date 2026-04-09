'use client'

import { useEffect, useState, useCallback } from 'react'
import { Outlet, useLocation } from 'react-router'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import { Sidebar } from './components/Sidebar'
import { Navbar } from './components/Navbar'
import { Breadcrumb, type BreadcrumbItem } from './components/Breadcrumb'
import { PATHS } from '@/routes/paths'
import {
  BreadcrumbProvider,
  useBreadcrumbContext,
} from '@/contexts/BreadcrumbContext'

const MOBILE_BREAKPOINT = 768

function generateBreadcrumbItems(pathname: string): BreadcrumbItem[] {
  const items: BreadcrumbItem[] = [
    { label: '首页', path: PATHS.ADMIN_DASHBOARD },
  ]

  const segments = pathname.split('/').filter(Boolean)
  if (segments[0] === 'admin') segments.shift()
  if (segments.length === 0 || segments[0] === 'dashboard') return [{ label: '首页' }]

  const routeLabels: Record<string, string> = {
    cases: '案件', contracts: '合同', clients: '当事人', documents: '文书',
    settings: '设置', automation: '自动化工具', 'preservation-quotes': '财产保全询价',
    'document-recognition': '文书智能识别', new: '新建', edit: '编辑',
    user: '用户设置', system: '系统配置',
  }

  let currentPath = '/admin'
  segments.forEach((segment, index) => {
    const isLast = index === segments.length - 1
    const label = routeLabels[segment] || segment
    if (/^\d+$/.test(segment) || /^[a-f0-9-]{36}$/i.test(segment)) return
    currentPath += `/${segment}`
    items.push(isLast ? { label } : { label, path: currentPath })
  })

  return items
}

function AdminLayoutContent() {
  const location = useLocation()
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed)
  const toggleSidebar = useUIStore((state) => state.toggleSidebar)
  const setSidebarCollapsed = useUIStore((state) => state.setSidebarCollapsed)
  const navMode = useUIStore((state) => state.navMode)
  const { customItems } = useBreadcrumbContext()

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

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

  const breadcrumbItems = customItems ?? generateBreadcrumbItems(location.pathname)
  const isTopbarMode = navMode === 'topbar'
  const mainMarginLeft = isMobile || isTopbarMode ? 0 : sidebarCollapsed ? 68 : 240

  return (
    <div className="bg-background relative min-h-screen">
      {/* 桌面端 Sidebar */}
      {!isMobile && !isTopbarMode && (
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
      )}

      {/* 移动端遮罩 */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200',
          isMobile && mobileMenuOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={closeMobileMenu}
        aria-hidden="true"
      />

      {/* 移动端 Sidebar 抽屉 */}
      <div
        className={cn(
          'fixed left-0 top-0 z-50 h-full w-[280px] transition-transform duration-300 ease-out',
          isMobile && mobileMenuOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <button
          onClick={closeMobileMenu}
          className="text-muted-foreground hover:text-foreground hover:bg-accent/50 dark:hover:bg-accent/30 absolute right-2 top-4 z-50 rounded-lg p-2 transition-colors duration-200"
          aria-label="关闭菜单"
        >
          <X className="size-5" />
        </button>
        <Sidebar collapsed={false} onToggle={closeMobileMenu} />
      </div>

      {/* 主内容区域 */}
      <div
        className="flex min-h-screen flex-col transition-[margin-left] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)]"
        style={{ marginLeft: mainMarginLeft }}
      >
        <Navbar onMenuClick={handleMobileMenuClick} showTopNav={isTopbarMode && !isMobile} />

        <main className="flex-1 p-4 md:p-6 lg:p-8">
          <div className="mb-4 md:mb-6">
            <Breadcrumb items={breadcrumbItems} />
          </div>
          <Outlet />
        </main>

        <footer className="border-border border-t px-4 py-4 md:px-6 lg:px-8">
          <p className="text-muted-foreground text-center text-xs">
            © {new Date().getFullYear()} 法穿 AI. All rights reserved.
          </p>
        </footer>
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
