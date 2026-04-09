'use client'

import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import { ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useUIStore } from '@/stores/ui'
import {
  menuConfig, isMenuGroup, findGroupByPath,
  type MenuItem, type MenuGroup, type TopLevelMenuItem,
} from './menu-config'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

function TopLevelMenuItemComponent({ item, collapsed, isActive }: {
  item: TopLevelMenuItem; collapsed: boolean; isActive: boolean
}) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
      className={cn(
        'flex items-center gap-3 h-10 px-3 rounded-lg mx-2 transition-all duration-150 group relative',
        'text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent',
        isActive && 'bg-sidebar-primary text-sidebar-primary-foreground hover:bg-sidebar-primary/90 shadow-sm dark:shadow-sidebar-primary/20',
        collapsed && 'justify-center mx-1 px-0',
      )}
    >
      <Icon className={cn('w-5 h-5 shrink-0', isActive && 'text-sidebar-primary-foreground')} />
      {!collapsed && <span className="text-sm font-medium truncate">{item.label}</span>}
      {collapsed && (
        <div className="absolute left-full ml-3 px-2.5 py-1.5 rounded-md bg-popover text-popover-foreground text-sm font-medium shadow-lg border border-border dark:shadow-xl dark:shadow-black/20 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 whitespace-nowrap z-50 pointer-events-none">
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
        'text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent',
        isActive && 'bg-sidebar-accent text-sidebar-primary font-medium',
      )}
    >
      <Icon className={cn('w-4 h-4 shrink-0', isActive && 'text-sidebar-primary')} />
      <span className="text-sm truncate">{item.label}</span>
    </NavLink>
  )
}

function MenuGroupComponent({ group, collapsed, isExpanded, onToggle, activeItemPath }: {
  group: MenuGroup; collapsed: boolean; isExpanded: boolean; onToggle: () => void; activeItemPath: string | null
}) {
  const Icon = group.icon
  const hasActiveItem = group.items.some((item) => activeItemPath?.startsWith(item.path))

  return (
    <div>
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center gap-3 h-10 px-3 rounded-lg mx-2 transition-all duration-150 group relative',
          'text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent',
          hasActiveItem && 'text-sidebar-foreground font-medium',
          collapsed && 'justify-center mx-1 px-0',
        )}
        style={{ width: collapsed ? 'calc(100% - 8px)' : 'calc(100% - 16px)' }}
      >
        {Icon && <Icon className={cn('w-5 h-5 shrink-0', hasActiveItem && 'text-primary')} />}
        {!collapsed && (
          <>
            <span className="flex-1 text-left text-sm font-medium truncate">{group.label}</span>
            <ChevronDown className={cn('w-4 h-4 text-muted-foreground transition-transform duration-200', isExpanded && 'rotate-180')} />
          </>
        )}
        {collapsed && (
          <div className="absolute left-full ml-3 py-2 rounded-lg min-w-[160px] bg-popover text-popover-foreground shadow-lg border border-border dark:shadow-xl dark:shadow-black/25 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 z-50">
            <div className="px-3 pb-1.5 mb-1 text-xs font-semibold text-muted-foreground border-b border-border">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-sidebar-accent transition-colors duration-150',
                  activeItemPath?.startsWith(item.path) && 'text-sidebar-primary bg-sidebar-accent font-medium',
                )}
              >
                <item.icon className="w-4 h-4" />{item.label}
              </NavLink>
            ))}
          </div>
        )}
      </button>

      {/* 子菜单 — CSS transition 替代 framer-motion */}
      {!collapsed && (
        <div
          className="overflow-hidden transition-all duration-200 ease-in-out"
          style={{
            maxHeight: isExpanded ? `${group.items.length * 40 + 8}px` : '0px',
            opacity: isExpanded ? 1 : 0,
          }}
        >
          <div className="mt-1 ml-4 mr-2 pl-4 border-l border-sidebar-border space-y-0.5">
            {group.items.map((item) => (
              <SubMenuItem key={item.id} item={item} isActive={activeItemPath?.startsWith(item.path) ?? false} />
            ))}
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

  useEffect(() => {
    const groupId = findGroupByPath(location.pathname)
    if (groupId && !expandedGroups.includes(groupId)) {
      setExpandedGroups([...expandedGroups, groupId])
    }
  }, [location.pathname, expandedGroups, setExpandedGroups])

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen flex flex-col',
        'bg-sidebar border-r border-sidebar-border',
        'transition-[width] duration-250 ease-[cubic-bezier(0.4,0,0.2,1)]',
      )}
      style={{ width: collapsed ? 68 : 240 }}
    >
      {/* Logo */}
      <NavLink
        to="/admin/dashboard"
        className={cn(
          'flex items-center h-16 px-4 shrink-0 relative border-b border-sidebar-border',
          'transition-all duration-200 hover:opacity-90 cursor-pointer dark:hover:bg-sidebar-accent/30',
          collapsed ? 'justify-center' : 'justify-start',
        )}
      >
        {collapsed ? (
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/30 dark:shadow-violet-500/20">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="text-white">
              <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" opacity="0.9"/>
              <path d="M2 17l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        ) : (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-md shadow-violet-500/25 dark:shadow-violet-500/15">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-white">
                <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" opacity="0.9"/>
                <path d="M2 17l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div className="flex flex-col">
              <span className="text-base font-semibold tracking-tight text-foreground leading-tight">法穿 AI</span>
              <span className="text-[10px] text-muted-foreground/80 tracking-wide">Legal Tech</span>
            </div>
          </div>
        )}
      </NavLink>

      {/* 菜单 */}
      <nav className={cn('flex-1 py-3', collapsed ? 'overflow-hidden' : 'overflow-y-auto')}>
        <div className="space-y-1">
          {menuConfig.map((item) =>
            isMenuGroup(item) ? (
              <MenuGroupComponent
                key={item.id}
                group={item}
                collapsed={collapsed}
                isExpanded={expandedGroups.includes(item.id)}
                onToggle={() => toggleGroup(item.id)}
                activeItemPath={location.pathname}
              />
            ) : (
              <TopLevelMenuItemComponent
                key={item.id}
                item={item}
                collapsed={collapsed}
                isActive={location.pathname === item.path}
              />
            )
          )}
        </div>
      </nav>

      {/* 收起/展开按钮 */}
      <div className={cn('p-3 border-t border-sidebar-border shrink-0', collapsed && 'flex justify-center')}>
        <Button
          variant="ghost"
          size={collapsed ? 'icon' : 'sm'}
          onClick={onToggle}
          className={cn('h-9 transition-all duration-150', !collapsed && 'w-full justify-start gap-2')}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <><ChevronLeft className="w-4 h-4" /><span className="text-sm">收起</span></>}
        </Button>
      </div>
    </aside>
  )
}

export default Sidebar
