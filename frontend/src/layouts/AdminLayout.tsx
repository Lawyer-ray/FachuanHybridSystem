'use client'

import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { motion, AnimatePresence } from 'framer-motion'
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

/**
 * 根据路由路径生成面包屑项
 */
function generateBreadcrumbItems(pathname: string): BreadcrumbItem[] {
  const items: BreadcrumbItem[] = [
    { label: '首页', path: PATHS.ADMIN_DASHBOARD },
  ]

  const segments = pathname.split('/').filter(Boolean)

  if (segments[0] === 'admin') {
    segments.shift()
  }

  if (segments.length === 0 || segments[0] === 'dashboard') {
    return [{ label: '首页' }]
  }

  const routeLabels: Record<string, string> = {
    cases: '案件',
    contracts: '合同',
    clients: '当事人',
    documents: '文书',
    settings: '设置',
    automation: '自动化工具',
    'preservation-quotes': '财产保全询价',
    'document-recognition': '文书智能识别',
    new: '新建',
    edit: '编辑',
    user: '用户设置',
    system: '系统配置',
  }

  let currentPath = '/admin'

  segments.forEach((segment, index) => {
    const isLast = index === segments.length - 1
    const label = routeLabels[segment] || segment

    if (/^\d+$/.test(segment) || /^[a-f0-9-]{36}$/i.test(segment)) {
      return
    }

    currentPath += `/${segment}`

    if (isLast) {
      items.push({ label })
    } else {
      items.push({ label, path: currentPath })
    }
  })

  return items
}

/**
 * AdminLayoutContent - 后台管理主布局内容组件
 */
function AdminLayoutContent() {
  const location = useLocation()

  // UI Store 状态
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed)
  const toggleSidebar = useUIStore((state) => state.toggleSidebar)
  const setSidebarCollapsed = useUIStore((state) => state.setSidebarCollapsed)
  const navMode = useUIStore((state) => state.navMode)

  // 面包屑上下文
  const { customItems } = useBreadcrumbContext()

  // 移动端 Sidebar 抽屉状态
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // 是否为移动端
  const [isMobile, setIsMobile] = useState(false)

  /**
   * 监听窗口大小变化
   */
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)

      if (mobile && !sidebarCollapsed) {
        setSidebarCollapsed(true)
      }
    }

    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [setSidebarCollapsed, sidebarCollapsed])

  /**
   * 路由变化时关闭移动端菜单
   */
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  const handleMobileMenuClick = () => {
    setMobileMenuOpen(true)
  }

  const closeMobileMenu = () => {
    setMobileMenuOpen(false)
  }

  const breadcrumbItems = customItems ?? generateBreadcrumbItems(location.pathname)

  // 计算主内容区域的左边距（仅 sidebar 模式）
  const isTopbarMode = navMode === 'topbar'
  const mainMarginLeft = isMobile || isTopbarMode ? 0 : sidebarCollapsed ? 72 : 260

  return (
    <div className="min-h-screen bg-background relative">
      {/* 桌面端 Sidebar（sidebar 模式） */}
      {!isMobile && !isTopbarMode && (
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
      )}

      {/* 移动端 Sidebar 抽屉 */}
      <AnimatePresence>
        {isMobile && mobileMenuOpen && (
          <>
            {/* 遮罩层 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
              onClick={closeMobileMenu}
              aria-hidden="true"
            />

            {/* Sidebar 抽屉 */}
            <motion.div
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{
                type: 'spring',
                damping: 25,
                stiffness: 300,
              }}
              className="fixed left-0 top-0 z-50 h-full w-[280px]"
            >
              {/* 关闭按钮 */}
              <button
                onClick={closeMobileMenu}
                className={cn(
                  'absolute right-2 top-4 z-50',
                  'p-2 rounded-lg',
                  'text-muted-foreground hover:text-foreground',
                  'hover:bg-accent/50 dark:hover:bg-accent/30',
                  'transition-colors duration-200'
                )}
                aria-label="关闭菜单"
              >
                <X className="h-5 w-5" />
              </button>

              <Sidebar collapsed={false} onToggle={closeMobileMenu} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* 主内容区域 */}
      <motion.div
        initial={false}
        animate={{ marginLeft: mainMarginLeft }}
        transition={{
          duration: 0.3,
          ease: [0.25, 0.46, 0.45, 0.94],
        }}
        className="flex flex-col min-h-screen"
      >
        {/* 顶部导航栏 */}
        <Navbar
          onMenuClick={handleMobileMenuClick}
          showTopNav={isTopbarMode && !isMobile}
        />

        {/* 页面内容 */}
        <main className="flex-1 p-4 md:p-6 lg:p-8">
          {/* 面包屑导航 */}
          <div className="mb-4 md:mb-6">
            <Breadcrumb items={breadcrumbItems} />
          </div>

          {/* 子路由内容 */}
          <Outlet />
        </main>

        {/* 页脚 */}
        <footer className="py-4 px-4 md:px-6 lg:px-8 border-t border-border">
          <p className="text-xs text-muted-foreground text-center">
            © {new Date().getFullYear()} 法穿 AI. All rights reserved.
          </p>
        </footer>
      </motion.div>
    </div>
  )
}

/**
 * AdminLayout - 后台管理主布局组件
 */
export function AdminLayout() {
  return (
    <BreadcrumbProvider>
      <AdminLayoutContent />
    </BreadcrumbProvider>
  )
}

export default AdminLayout
