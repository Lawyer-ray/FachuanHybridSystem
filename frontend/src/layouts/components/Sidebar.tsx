import { useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router'
import { ChevronLeft, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import {
  menuConfig,
  bottomMenuItems,
  isMenuGroup,
  findGroupByPath,
  type MenuItem,
  type MenuGroup,
  type TopLevelMenuItem,
} from './menu-config'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

function TopLevelItem({ item, collapsed, isActive }: {
  item: TopLevelMenuItem; collapsed: boolean; isActive: boolean
}) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
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
}

function SubMenuItem({ item, isActive }: { item: MenuItem; isActive: boolean }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
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
}

function GroupMenu({ group, collapsed, isExpanded, onToggle, activePath }: {
  group: MenuGroup; collapsed: boolean; isExpanded: boolean; onToggle: () => void; activePath: string
}) {
  const Icon = group.icon
  const hasActive = group.items.some((item) => activePath.startsWith(item.path))

  return (
    <div>
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center gap-3 h-10 px-3 rounded-md mx-2 transition-all duration-150 group relative',
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
        {collapsed && (
          <div className="absolute left-full ml-3 py-2 rounded-lg min-w-[160px] bg-[#27272a] text-white shadow-lg border border-[#3f3f46] opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 z-50">
            <div className="px-3 pb-1.5 mb-1 text-xs font-semibold text-[#71717a] border-b border-[#3f3f46]">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 text-[13px] hover:bg-[#27272a] transition-colors duration-150',
                  activePath.startsWith(item.path) && 'text-white bg-[#27272a] font-medium',
                )}
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </NavLink>
            ))}
          </div>
        )}
      </button>

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
}

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
      )}
      style={{ width: collapsed ? 56 : 220 }}
    >
      {/* Brand */}
      <NavLink
        to="/admin/dashboard"
        className={cn(
          'flex items-center h-14 px-4 shrink-0',
          'border-b border-[rgba(255,255,255,0.08)]',
          'transition-all duration-200 hover:opacity-90',
          collapsed ? 'justify-center' : 'gap-2.5',
        )}
      >
        {!collapsed && (
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
          {menuConfig.filter((i): i is TopLevelMenuItem => !isMenuGroup(i)).map((item) => (
            <TopLevelItem
              key={item.id}
              item={item}
              collapsed={collapsed}
              isActive={location.pathname === item.path}
            />
          ))}

          {/* 分组 */}
          {menuConfig.filter(isMenuGroup).map((group) => (
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
