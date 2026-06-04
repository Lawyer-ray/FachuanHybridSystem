import { memo, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import { ChevronLeft, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import { prefetchRoute } from '@/lib/prefetch'
import {
  menuConfig,
  bottomMenuItems,
  isMenuGroup,
  findGroupByPath,
  type MenuItem,
  type MenuGroup,
  type TopLevelMenuItem,
} from './menu-config'

/** 路径 → 页面 dynamic import 映射，用于 hover 预加载 */
/** 静态菜单配置，只计算一次 */
const topLevelMenuItems = menuConfig.filter((i): i is TopLevelMenuItem => !isMenuGroup(i))
const groupMenuItems = menuConfig.filter(isMenuGroup)

const routePrefetchMap: Record<string, () => Promise<unknown>> = {
  '/admin/dashboard': () => import('@/pages/dashboard/DashboardPage'),
  '/admin/workbench': () => import('@/features/workbench/WorkbenchPage'),
  '/admin/inbox': () => import('@/pages/dashboard/inbox/InboxListPage'),
  '/admin/clients': () => import('@/pages/dashboard/clients/ClientListPage'),
  '/admin/cases': () => import('@/pages/dashboard/cases/CaseListPage'),
  '/admin/contracts': () => import('@/pages/dashboard/contracts/ContractListPage'),
  '/admin/settings': () => import('@/pages/dashboard/settings/SettingsOverviewPage'),
  '/admin/organization': () => import('@/pages/dashboard/organization/OrganizationPage'),
  '/admin/automation': () => import('@/pages/dashboard/automation/AutomationIndexPage'),
  '/admin/templates': () => import('@/pages/dashboard/templates/TemplateListPage'),
  '/admin/tools/court-sms': () => import('@/pages/dashboard/tools/CourtSmsPage'),
  '/admin/tools/courier-tracking': () => import('@/pages/dashboard/tools/CourierTrackingPage'),
  '/admin/tools/element-convert': () => import('@/pages/dashboard/tools/ElementConvertPage'),
  '/admin/tools/lpr-calculator': () => import('@/pages/dashboard/tools/LprCalculatorPage'),
  '/admin/tools/content-ops': () => import('@/pages/dashboard/tools/ContentOpsPage'),
  '/admin/reminders': () => import('@/pages/dashboard/reminders'),
  '/admin/task-queue': () => import('@/pages/dashboard/task-queue/TaskQueuePage'),
  '/admin/logs': () => import('@/pages/dashboard/logs/LogsPage'),
}

function handlePrefetch(path: string) {
  const fn = routePrefetchMap[path]
  if (fn) prefetchRoute(path, fn)
}

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

const TopLevelItem = memo(function TopLevelItem({ item, collapsed, isActive }: {
  item: TopLevelMenuItem; collapsed: boolean; isActive: boolean
}) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
      onMouseEnter={() => handlePrefetch(item.path)}
      onFocus={() => handlePrefetch(item.path)}
      className={cn(
        'flex items-center gap-3 h-10 px-3 rounded-md mx-2 transition-all duration-150 group relative',
        'text-[#a1a1aa] hover:text-white hover:bg-[#27272a]',
        isActive && 'bg-[#27272a] text-white font-medium',
        collapsed && 'justify-center mx-1 px-0',
      )}
    >
      <Icon className="w-[18px] h-[18px] shrink-0" />
      {!collapsed && <span className="text-[13px] font-medium truncate">{item.label}</span>}
      {collapsed && (
        <div className="absolute left-full ml-3 px-2.5 py-1.5 rounded-md bg-[#27272a] text-white text-[13px] font-medium shadow-lg border border-[#3f3f46] opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 whitespace-nowrap z-50 pointer-events-none">
          {item.label}
        </div>
      )}
    </NavLink>
  )
})

const SubMenuItem = memo(function SubMenuItem({ item, isActive }: { item: MenuItem; isActive: boolean }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
      onMouseEnter={() => handlePrefetch(item.path)}
      onFocus={() => handlePrefetch(item.path)}
      className={cn(
        'flex items-center gap-2.5 h-9 px-3 rounded-md transition-all duration-150',
        'text-[#a1a1aa] hover:text-white hover:bg-[#27272a]',
        isActive && 'bg-[#27272a] text-white font-medium',
      )}
    >
      <Icon className="w-4 h-4 shrink-0" />
      <span className="text-[13px] truncate">{item.label}</span>
    </NavLink>
  )
})

const GroupMenu = memo(function GroupMenu({ group, collapsed, isExpanded, onToggle, activePath }: {
  group: MenuGroup; collapsed: boolean; isExpanded: boolean; onToggle: () => void; activePath: string
}) {
  const Icon = group.icon
  const hasActive = group.items.some((item) => activePath.startsWith(item.path))
  const [popoverOpen, setPopoverOpen] = useState(false)
  const [buttonRect, setButtonRect] = useState<DOMRect | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  // Click outside to close (check both button area and popover)
  useEffect(() => {
    if (!popoverOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (popoverRef.current?.contains(target)) return
      setPopoverOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [popoverOpen])

  // Close popover on route change
  const prevPath = useRef(activePath)
  useEffect(() => {
    if (activePath !== prevPath.current) {
      prevPath.current = activePath
      setPopoverOpen(false)
    }
  }, [activePath])

  const handleButtonClick = (e: React.MouseEvent) => {
    if (collapsed) {
      // Measure button position for fixed popover placement
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      setButtonRect(rect)
      setPopoverOpen((prev) => !prev)
    } else {
      onToggle()
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={handleButtonClick}
        className={cn(
          'w-full flex items-center gap-3 h-10 px-3 rounded-md mx-2 transition-all duration-150 group',
          'text-[#a1a1aa] hover:text-white hover:bg-[#27272a]',
          hasActive && 'text-white',
          collapsed && 'justify-center mx-1 px-0',
        )}
        style={{ width: collapsed ? 'calc(100% - 8px)' : 'calc(100% - 16px)' }}
      >
        {Icon && <Icon className="w-[18px] h-[18px] shrink-0" />}
        {!collapsed && (
          <>
            <span className="flex-1 text-left text-[13px] font-medium truncate">{group.label}</span>
            <ChevronDown className={cn('w-4 h-4 text-[#71717a] transition-transform duration-200', isExpanded && 'rotate-180')} />
          </>
        )}
      </button>

      {/* Collapsed: click-triggered popover (fixed positioning to escape overflow:hidden) */}
      {collapsed && popoverOpen && buttonRect && (
        <div
          ref={popoverRef}
          className="fixed rounded-xl overflow-hidden"
          style={{
            left: buttonRect.right + 10,
            top: buttonRect.top - 4,
            zIndex: 9999,
            minWidth: 180,
            animation: 'popover-in 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          {/* Arrow */}
          <div
            className="absolute -left-1.5 top-5 w-3 h-3 rotate-45 bg-[#1e1e21] border-l border-b border-[#333338]"
          />
          {/* Content */}
          <div className="relative bg-[#1e1e21] border border-[#333338] rounded-xl shadow-2xl shadow-black/40 py-1.5">
            <div className="px-3.5 pt-1 pb-2 mb-1 flex items-center gap-2">
              {Icon && <Icon className="w-3.5 h-3.5 text-[#6366f1]" />}
              <span className="text-[11px] font-semibold text-[#71717a] tracking-wide uppercase">{group.label}</span>
            </div>
            {group.items.map((item) => {
              const isActive = activePath.startsWith(item.path)
              return (
                <NavLink
                  key={item.id}
                  to={item.path}
                  onMouseEnter={() => handlePrefetch(item.path)}
                  onFocus={() => handlePrefetch(item.path)}
                  className={cn(
                    'flex items-center gap-3 mx-1.5 px-2.5 py-2 rounded-lg text-[13px] transition-all duration-150',
                    'hover:bg-white/[0.06]',
                    isActive
                      ? 'text-white bg-white/[0.08] font-medium'
                      : 'text-[#a1a1aa]',
                  )}
                >
                  <span className={cn(
                    'flex items-center justify-center w-7 h-7 rounded-lg transition-colors duration-150',
                    isActive ? 'bg-[#6366f1]/20 text-[#818cf8]' : 'bg-white/[0.04] text-[#71717a]',
                  )}>
                    <item.icon className="w-4 h-4" />
                  </span>
                  <span className="flex-1">{item.label}</span>
                  {isActive && <span className="w-1.5 h-1.5 rounded-full bg-[#6366f1]" />}
                </NavLink>
              )
            })}
          </div>
        </div>
      )}

      {/* Expanded: inline sub-items */}
      {!collapsed && (
        <div
          className="grid transition-[grid-template-rows] duration-200 ease-in-out"
          style={{ gridTemplateRows: isExpanded ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden min-h-0">
            <div
              className="mt-1 ml-4 mr-2 pl-4 border-l border-[#27272a] space-y-0.5 transition-opacity duration-200 ease-in-out"
              style={{ opacity: isExpanded ? 1 : 0 }}
            >
              {group.items.map((item) => (
                <SubMenuItem key={item.id} item={item} isActive={activePath.startsWith(item.path)} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
})

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation()
  const expandedGroups = useUIStore((s) => s.expandedGroups)
  const toggleGroup = useUIStore((s) => s.toggleGroup)
  const setExpandedGroups = useUIStore((s) => s.setExpandedGroups)

  const prevPathname = useRef(location.pathname)
  useEffect(() => {
    if (location.pathname !== prevPathname.current) {
      prevPathname.current = location.pathname
      const groupId = findGroupByPath(location.pathname)
      if (groupId) {
        const current = useUIStore.getState().expandedGroups
        if (!current.includes(groupId)) {
          setExpandedGroups([...current, groupId])
        }
      }
    }
  }, [location.pathname, setExpandedGroups])

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen flex flex-col',
        'bg-[#18181b] border-r border-[#27272a]',
        'transition-[width] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]',
        'will-change-[width]',
      )}
      style={{ width: collapsed ? 56 : 220 }}
    >
      {/* Brand */}
      <NavLink
        to="/admin/dashboard"
        onMouseEnter={() => handlePrefetch('/admin/dashboard')}
        className={cn(
          'flex items-center h-12 px-4 shrink-0',
          'border-b border-[rgba(255,255,255,0.08)]',
          'transition-all duration-200 hover:opacity-90',
          collapsed ? 'justify-center' : 'gap-2.5',
        )}
      >
        {collapsed ? (
          <span className="text-[15px] font-bold text-white">FC</span>
        ) : (
          <span className="text-[15px] font-bold text-white tracking-wide">法穿AI Copilot</span>
        )}
      </NavLink>

      {/* 折叠按钮 - 侧边栏右侧中间 */}
      <button
        onClick={onToggle}
        className="absolute top-1/2 -translate-y-1/2 -right-3 z-50 w-6 h-6 rounded-full bg-[#27272a] border border-[#3f3f46] flex items-center justify-center text-[#a1a1aa] hover:text-white hover:bg-[#3f3f46] transition-colors"
      >
        <ChevronLeft className={cn('w-3 h-3 transition-transform', collapsed && 'rotate-180')} />
      </button>

      {/* 菜单 */}
      <nav className={cn('flex-1 py-3', collapsed ? 'overflow-hidden' : 'overflow-y-auto')}>
        <div className="space-y-1">
          {/* Dashboard 顶级项 */}
          {topLevelMenuItems.map((item) => (
            <TopLevelItem
              key={item.id}
              item={item}
              collapsed={collapsed}
              isActive={location.pathname === item.path}
            />
          ))}

          {/* 分组 */}
          {groupMenuItems.map((group) => (
            <div key={group.id}>
              <GroupMenu
                group={group}
                collapsed={collapsed}
                isExpanded={expandedGroups.includes(group.id)}
                onToggle={() => toggleGroup(group.id)}
                activePath={location.pathname}
              />
            </div>
          ))}
        </div>
      </nav>

      {/* 底部固定菜单 */}
      <div className="border-t border-[rgba(255,255,255,0.08)] py-2 shrink-0">
        {bottomMenuItems.map((item) => (
          <TopLevelItem
            key={item.id}
            item={item}
            collapsed={collapsed}
            isActive={location.pathname.startsWith(item.path)
              || location.pathname.startsWith('/admin/settings')
              || location.pathname.startsWith('/admin/organization')}
          />
        ))}
      </div>
    </aside>
  )
}

export default Sidebar
