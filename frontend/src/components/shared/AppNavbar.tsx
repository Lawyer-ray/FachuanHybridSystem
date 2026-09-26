import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { LogOut, Menu, Plus, Search } from 'lucide-react'

import { useAuth } from '@/features/auth/store'
import { Button } from '@/components/ui/button'

/**
 * 全局顶层导航（全站唯一一套，首页 / 材料预处理等所有页面共用）。
 *
 * 合并自原「首页 TopNav」与「材料预处理页内联 header」：此前两处各写一份，
 * 跨页面跳转时导航会变形（一边有 logo + 退出，一边没有）。按 frontend/CLAUDE.md
 * 的提权规则，navbar 被 ≥2 个 feature 使用，故收敛到 components/shared/。
 */
export interface AppNavbarProps {
  /** 未实现入口的回调（给 toast 提示） */
  onNotify?: (msg: string) => void
  /** 退出登录后跳转；不传则默认回 /login */
  onLogout?: () => void
}

const NOT_READY: Record<string, string> = {
  '/workbench': '办案工作台正在开发中',
  '/ledger': '案件台账正在开发中',
}

export function AppNavbar({ onNotify, onLogout }: AppNavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)

  const notify = (msg: string) => onNotify?.(msg)

  const handleLogout = () => {
    logout()
    onLogout?.()
  }

  return (
    <header className="sticky top-0 z-50 flex h-[54px] items-center gap-2 border-b border-border bg-card/80 px-[22px] backdrop-blur-[14px]">
      <button
        type="button"
        className="hidden h-8 w-8 items-center justify-center rounded-[8px] text-foreground max-[760px]:flex"
        onClick={() => setMenuOpen((v) => !v)}
        aria-label="菜单"
      >
        <Menu className="h-[18px] w-[18px]" />
      </button>

      {/* 品牌：黑底「法」字 + 产品名 */}
      <Link to="/" className="flex flex-none items-center gap-[9px] pr-1.5 no-underline">
        <span className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] bg-foreground text-[13px] font-bold text-background">
          法
        </span>
        <span className="text-[14px] font-bold whitespace-nowrap tracking-[-0.01em] text-foreground">
          法穿 <span className="text-[12.5px] font-medium text-muted-foreground">AI Copilot</span>
        </span>
      </Link>

      <nav
        className={`items-center gap-[2px] max-[760px]:fixed max-[760px]:inset-x-0 max-[760px]:top-[54px] max-[760px]:z-49 max-[760px]:flex-col max-[760px]:items-stretch max-[760px]:border-b max-[760px]:border-border max-[760px]:bg-card max-[760px]:p-2 max-[760px]:shadow-[0_12px_24px_rgba(0,0,0,.08)] ${
          menuOpen ? 'flex' : 'max-[760px]:hidden'
        } md:flex`}
      >
        <NavLink to="/" label="首页" active={pathname === '/'} onClick={() => setMenuOpen(false)} />
        <NavLink
          to="/material-prep"
          label="材料预处理"
          active={pathname.startsWith('/material-prep')}
          onClick={() => setMenuOpen(false)}
        />
        {Object.entries(NOT_READY).map(([path, msg]) => (
          <button
            key={path}
            type="button"
            className="cursor-pointer rounded-[8px] px-3 py-[7px] text-left text-[13.5px] font-medium whitespace-nowrap text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => {
              setMenuOpen(false)
              notify(msg)
            }}
          >
            {path === '/workbench' ? '办案' : '台账'}
          </button>
        ))}
      </nav>

      {/* 全局检索 */}
      <button
        type="button"
        className="ml-auto hidden h-8 items-center gap-[7px] rounded-[8px] border border-border bg-secondary px-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-input hover:bg-card sm:flex"
        onClick={() => notify('全局检索（跨案件 / 材料 / 当事人）正在开发中')}
      >
        <Search className="h-[13px] w-[13px]" />
        <span>检索</span>
        <kbd className="rounded-[4px] border border-input bg-card px-[5px] py-[1px] text-[10px] text-muted-foreground">⌘K</kbd>
      </button>

      <button
        type="button"
        className="flex h-8 items-center gap-1.5 rounded-[8px] bg-foreground px-3.5 text-[12.5px] font-semibold whitespace-nowrap text-background transition-opacity hover:opacity-85"
        onClick={() => notify('新建案件：可先把材料上传到「材料预处理」归案')}
      >
        <Plus className="h-3 w-3" strokeWidth={2.5} />
        新建案件
      </button>

      {/* 用户区：头像 + 退出 */}
      <div className="ml-1 flex flex-none items-center gap-1.5">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full bg-foreground text-[11px] font-semibold text-background"
          title={user?.username || '个人中心'}
        >
          {(user?.username || '我').trim().slice(0, 1) || '我'}
        </span>
        <Button size="sm" variant="ghost" onClick={handleLogout} title="退出登录">
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">退出</span>
        </Button>
      </div>
    </header>
  )
}

function NavLink({
  to,
  label,
  active,
  onClick,
}: {
  to: string
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <Link
      to={to}
      onClick={onClick}
      className={`cursor-pointer rounded-[8px] px-3 py-[7px] text-[13.5px] font-medium whitespace-nowrap no-underline transition-colors hover:bg-secondary hover:text-foreground ${
        active ? 'bg-secondary text-foreground' : 'text-secondary-foreground'
      }`}
    >
      {label}
    </Link>
  )
}
