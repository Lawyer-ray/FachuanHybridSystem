'use client'

import { useState, useRef, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  menuConfig,
  isMenuGroup,
  type MenuGroup,
  type TopLevelMenuItem,
} from './menu-config'

/**
 * 顶部导航菜单组件
 * 用于 topbar 模式下的水平导航
 */
export function TopNavMenu() {
  const location = useLocation()

  return (
    <nav className="flex items-center gap-1">
      {menuConfig.map((item) => {
        if (isMenuGroup(item)) {
          return (
            <DropdownMenu
              key={item.id}
              group={item}
              currentPath={location.pathname}
            />
          )
        }

        return (
          <TopLevelItem
            key={item.id}
            item={item}
            isActive={location.pathname === item.path}
          />
        )
      })}
    </nav>
  )
}

/**
 * 顶级菜单项
 */
function TopLevelItem({
  item,
  isActive,
}: {
  item: TopLevelMenuItem
  isActive: boolean
}) {
  const Icon = item.icon

  return (
    <NavLink
      to={item.path}
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-lg',
        'text-sm font-medium transition-colors duration-200',
        'text-muted-foreground hover:text-foreground',
        'hover:bg-accent/50 dark:hover:bg-accent/30',
        isActive && [
          'bg-primary/10 text-primary',
          'dark:bg-primary/20 dark:text-primary',
        ]
      )}
    >
      <Icon className="w-4 h-4" />
      <span>{item.label}</span>
    </NavLink>
  )
}

/**
 * 下拉菜单组件
 */
function DropdownMenu({
  group,
  currentPath,
}: {
  group: MenuGroup
  currentPath: string
}) {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const Icon = group.icon
  const hasActiveItem = group.items.some((item) => currentPath.startsWith(item.path))

  // 点击外部关闭
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 鼠标悬停打开
  const handleMouseEnter = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsOpen(true)
  }

  // 鼠标离开延迟关闭
  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsOpen(false)
    }, 150)
  }

  return (
    <div
      ref={menuRef}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* 触发按钮 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg',
          'text-sm font-medium transition-colors duration-200',
          'text-muted-foreground hover:text-foreground',
          'hover:bg-accent/50 dark:hover:bg-accent/30',
          hasActiveItem && 'text-primary',
          isOpen && 'bg-accent/50 dark:bg-accent/30'
        )}
      >
        {Icon && <Icon className="w-4 h-4" />}
        <span>{group.label}</span>
        <ChevronDown
          className={cn(
            'w-3.5 h-3.5 transition-transform duration-200',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {/* 下拉菜单 */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute top-full left-0 mt-1 py-1.5 min-w-[180px]',
              'bg-popover text-popover-foreground',
              'rounded-lg shadow-lg border border-border',
              'dark:shadow-xl dark:shadow-black/25',
              'z-50'
            )}
          >
            {group.items.map((item) => {
              const ItemIcon = item.icon
              const isActive = currentPath.startsWith(item.path)

              return (
                <NavLink
                  key={item.id}
                  to={item.path}
                  onClick={() => setIsOpen(false)}
                  className={cn(
                    'flex items-center gap-2.5 px-3 py-2 mx-1.5 rounded-md',
                    'text-sm transition-colors duration-150',
                    'hover:bg-accent/50 dark:hover:bg-accent/30',
                    isActive && [
                      'bg-primary/10 text-primary',
                      'dark:bg-primary/20 dark:text-primary',
                    ]
                  )}
                >
                  <ItemIcon className="w-4 h-4" />
                  <span>{item.label}</span>
                </NavLink>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default TopNavMenu
