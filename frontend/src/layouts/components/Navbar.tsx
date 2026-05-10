import { useNavigate } from 'react-router'
import { Menu, LogOut, Home, Users, Settings, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/features/auth/api'
import { PATHS } from '@/routes/paths'
import { TopbarIcons } from '@/components/shared/TopbarIcons'
import { resolveMediaUrl } from '@/lib/api'

interface NavbarProps {
  onMenuClick: () => void
}

export function Navbar({ onMenuClick }: NavbarProps) {
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  const getAvatarInitials = (): string => {
    if (user?.real_name) return user.real_name.charAt(0)
    if (user?.username) return user.username.charAt(0).toUpperCase()
    return 'U'
  }

  const getDisplayName = (): string => {
    return user?.real_name || user?.username || '用户'
  }

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

  return (
    <header className="sticky top-0 z-30 flex items-center h-12 px-4 bg-background/95 border-b border-border">
      {/* 左侧：移动端汉堡菜单 */}
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden mr-2"
        onClick={onMenuClick}
        aria-label="打开菜单"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* 搜索框 */}
      <div
        className="hidden md:flex items-center gap-2 h-8 px-3 rounded-md bg-muted border border-border cursor-pointer hover:border-foreground/20 transition-colors w-64"
        onClick={() => {
          const isMac = navigator.userAgent.includes('Mac')
          const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: !isMac, metaKey: isMac })
          document.dispatchEvent(event)
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground shrink-0">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <span className="text-[13px] text-muted-foreground flex-1">搜索功能或输入命令...</span>
        <kbd className="text-[11px] text-muted-foreground bg-background px-1.5 py-0.5 rounded border border-border">{navigator.userAgent.includes('Mac') ? '⌘K' : 'Ctrl+K'}</kbd>
      </div>

      {/* 右侧区域 */}
      <div className="flex items-center gap-1 ml-auto">
        {/* Topbar 图标按钮 */}
        <div className="hidden md:flex">
          <TopbarIcons />
        </div>

        {/* 主题切换 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            >
              <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{theme === 'light' ? '暗色模式' : '亮色模式'}</TooltipContent>
        </Tooltip>

        {/* 用户下拉菜单 */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-2 px-2 h-8">
              <Avatar className="h-6 w-6">
                {user?.avatar_url && (
                  <AvatarImage src={resolveMediaUrl(user.avatar_url) ?? undefined} alt={getDisplayName()} />
                )}
                <AvatarFallback className="bg-[#27272a] text-[#a1a1aa] text-xs">
                  {getAvatarInitials()}
                </AvatarFallback>
              </Avatar>
              <div className="hidden sm:flex flex-col items-start">
                <span className="text-[13px] font-medium leading-tight">{getDisplayName()}</span>
                <span className="text-[10px] text-muted-foreground leading-tight">
                  {user?.is_admin ? '管理员' : '律师'}
                </span>
              </div>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem className="cursor-pointer" onClick={() => navigate(PATHS.ADMIN_SETTINGS_LAW_FIRM)}>
              <Home className="mr-2 h-4 w-4" />
              <span>律所设置</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer" onClick={() => navigate(PATHS.ADMIN_SETTINGS_TEAM)}>
              <Users className="mr-2 h-4 w-4" />
              <span>团队设置</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer" onClick={() => navigate(PATHS.ADMIN_SETTINGS_LAWYER)}>
              <Users className="mr-2 h-4 w-4" />
              <span>律师设置</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="cursor-pointer" onClick={() => navigate(PATHS.ADMIN_SETTINGS)}>
              <Settings className="mr-2 h-4 w-4" />
              <span>系统配置</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer text-destructive focus:text-destructive"
              onClick={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              <span>注销</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}

export default Navbar
