'use client'

import { NavLink, useNavigate } from 'react-router'
import { Menu, LogOut, User, PanelLeft, PanelTop } from 'lucide-react'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useAuthStore } from '@/stores/auth'
import { useUIStore, type NavMode } from '@/stores/ui'
import { authApi } from '@/features/auth/api'
import { PATHS } from '@/routes/paths'
import { TopNavMenu } from './TopNavMenu'

/**
 * Navbar 组件属性
 */
interface NavbarProps {
  /** 移动端汉堡菜单点击回调 */
  onMenuClick: () => void
  /** 是否显示顶部导航菜单（topbar 模式） */
  showTopNav?: boolean
}

/**
 * Navbar - 顶部导航栏组件
 *
 * 实现后台管理系统的顶部导航栏，包含：
 * - 移动端汉堡菜单按钮
 * - 顶部导航菜单（topbar 模式）
 * - 当前用户信息显示（用户名和头像）
 * - 主题切换按钮（明亮/暗夜模式）
 * - 导航模式切换按钮
 * - 登出按钮和功能
 */
export function Navbar({ onMenuClick, showTopNav = false }: NavbarProps) {
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const navMode = useUIStore((state) => state.navMode)
  const setNavMode = useUIStore((state) => state.setNavMode)

  /**
   * 获取用户头像显示的首字母
   */
  const getAvatarInitials = (): string => {
    if (user?.real_name) {
      return user.real_name.charAt(0).toUpperCase()
    }
    if (user?.username) {
      return user.username.charAt(0).toUpperCase()
    }
    return 'U'
  }

  /**
   * 获取显示的用户名
   */
  const getDisplayName = (): string => {
    return user?.real_name || user?.username || '用户'
  }

  /**
   * 处理登出操作
   */
  const handleLogout = async () => {
    try {
      await authApi.logout()
      logout()
      toast.success('已成功登出')
      navigate(PATHS.LOGIN)
    } catch {
      logout()
      navigate(PATHS.LOGIN)
    }
  }

  /**
   * 切换主题
   */
  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light')
  }

  /**
   * 切换导航模式
   */
  const toggleNavMode = () => {
    const newMode: NavMode = navMode === 'sidebar' ? 'topbar' : 'sidebar'
    setNavMode(newMode)
    toast.success(newMode === 'sidebar' ? '已切换为侧边栏模式' : '已切换为顶部导航模式')
  }

  return (
    <header
      className={cn(
        'sticky top-0 z-30',
        'flex items-center justify-between h-16 px-4 md:px-6',
        'bg-background/85 backdrop-blur-xl',
        'border-b border-border',
        'dark:bg-background/90 dark:border-border/80'
      )}
    >
      {/* 左侧 */}
      <div className="flex items-center gap-4">
        {/* 移动端汉堡菜单 */}
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onMenuClick}
          aria-label="打开菜单"
        >
          <Menu className="h-5 w-5" />
        </Button>

        {/* Logo（topbar 模式下显示） */}
        {showTopNav && (
          <NavLink
            to="/admin/dashboard"
            className="hidden md:flex items-center gap-2.5 mr-6 transition-opacity hover:opacity-80"
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-md shadow-violet-500/25">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-white">
                <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" opacity="0.9"/>
                <path d="M2 17l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="text-base font-semibold tracking-tight text-foreground">
              法穿 AI
            </span>
          </NavLink>
        )}

        {/* 顶部导航菜单（topbar 模式） */}
        {showTopNav && (
          <div className="hidden md:block">
            <TopNavMenu />
          </div>
        )}
      </div>

      {/* 右侧：用户信息和操作按钮 */}
      <div className="flex items-center gap-1">
        {/* 导航模式切换按钮 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleNavMode}
              aria-label="切换导航模式"
              className="hidden md:inline-flex"
            >
              {navMode === 'sidebar' ? (
                <PanelTop className="h-5 w-5" />
              ) : (
                <PanelLeft className="h-5 w-5" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {navMode === 'sidebar' ? '切换为顶部导航' : '切换为侧边栏'}
          </TooltipContent>
        </Tooltip>

        {/* 主题切换按钮 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label="切换主题"
              className="relative"
            >
              <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
              <span className="sr-only">切换主题</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {theme === 'light' ? '切换为暗色模式' : '切换为亮色模式'}
          </TooltipContent>
        </Tooltip>

        {/* 用户下拉菜单 */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className={cn(
                'flex items-center gap-2 px-2',
                'hover:bg-accent/50 dark:hover:bg-accent/30'
              )}
            >
              <Avatar className="h-8 w-8">
                <AvatarFallback
                  className={cn(
                    'bg-primary/10 text-primary',
                    'dark:bg-primary/20 dark:text-primary'
                  )}
                >
                  {getAvatarInitials()}
                </AvatarFallback>
              </Avatar>
              <span className="hidden sm:inline-block text-sm font-medium">
                {getDisplayName()}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium leading-none">
                  {getDisplayName()}
                </p>
                {user?.username && (
                  <p className="text-xs leading-none text-muted-foreground">
                    @{user.username}
                  </p>
                )}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer"
              onClick={() => navigate(PATHS.ADMIN_SETTINGS_USER)}
            >
              <User className="mr-2 h-4 w-4" />
              <span>用户设置</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer text-destructive focus:text-destructive"
              onClick={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              <span>登出</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}

export default Navbar
