import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LogOut, Menu, Plus, Search, User } from 'lucide-react'

import { useAuth, type User as AuthUser } from '@/features/auth'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { GlobalSearch } from '@/features/search'

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

/** 补拉当前用户信息的 query key（本组件独用，就地定义） */
const ORG_ME_KEY = ['organization-me'] as const

export function AppNavbar({ onNotify, onLogout }: AppNavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)
  const { pathname } = useLocation()
  const user = useAuth((s) => s.user)
  const setUser = useAuth((s) => s.setUser)
  const logout = useAuth((s) => s.logout)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // auth store 在刷新页面（init 路径）时只放了 {id:0, username:''} 占位，
  // 拿不到真实用户名。navbar 又得显示用户名，所以这里补拉一次
  // /organization/me（登录时也拉过，属幂等只读）。走 react-query 带缓存，
  // 只在没有用户名时启用，避免每次挂载都请求。
  const meQuery = useQuery({
    queryKey: ORG_ME_KEY,
    // queryFn 只做纯取数（类型复用 auth 域的 User 投影），store 回写放到
    // 下面的 useEffect——queryFn 内写外部 store 会在 react-query 缓存重放 /
    // 严格模式双执行时产生隐藏副作用
    queryFn: () => api.get('organization/me').json<AuthUser>(),
    enabled: !user?.username,
    staleTime: 5 * 60_000,
    retry: false,
  })

  // 拉到用户名后回写一次 store：让用户菜单 / 依赖 useAuth 的其它组件同步显示。
  // enabled 仍由 user.username 翻转控制，回写后 query 转禁用、data 保留，effect 不再触发。
  useEffect(() => {
    const me = meQuery.data
    if (me?.username) setUser({ id: me.id, username: me.username })
  }, [meQuery.data, setUser])

  const notify = (msg: string) => onNotify?.(msg)

  // ⌘K / Ctrl+K 唤起全局检索。dialog 已打开时不再重复触发。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleLogout = () => {
    setLogoutOpen(false)
    logout()
    // 清空 react-query 缓存：否则换账号登录后在 staleTime 窗口内
    // 会直接命中上一账号的日历/收件箱/合同等缓存数据
    queryClient.clear()
    // 清空材料预处理阅读器状态与 PDF/字节缓存（换账号不得残留上一账号的材料内容）。
    // 走动态 import：这条依赖链上有 pdfjs-dist（~1MB 懒加载 chunk），
    // 静态引会把整个材料预处理域拖进首屏包（AppNavbar 经 HomePage 进 entry chunk）
    void import('@/features/material-prep/store')
      .then((m) => m.useReader.getState().resetAll())
      .catch(() => {})
    void import('@/lib/pdf')
      .then((m) => m.clearPdfCache())
      .catch(() => {})
    // react-router 的 navigate 返回 void | Promise<void>，这里 fire-and-forget
    void navigate('/login', { replace: true })
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

      {/* 品牌：产品名（点击回首页） */}
      <Link to="/" className="flex flex-none items-center pr-1.5 no-underline">
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
        <NavLink
          to="/cases"
          label="办案"
          active={pathname.startsWith('/cases')}
          onClick={() => setMenuOpen(false)}
        />
      </nav>

      {/* 全局检索 */}
      <button
        type="button"
        className="ml-auto hidden h-8 items-center gap-[7px] rounded-[8px] border border-border bg-secondary px-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-input hover:bg-card sm:flex"
        onClick={() => setSearchOpen(true)}
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

      {/* 用户区：点头像开菜单；退出走确认弹窗——不能点一下就登出 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="ml-1 flex flex-none items-center gap-1.5 rounded-full py-[2px] pr-2 pl-[2px] transition-colors hover:bg-secondary"
            aria-label="用户菜单"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-foreground text-background">
              <User className="h-3.5 w-3.5" />
            </span>
            <span className="hidden max-w-[88px] truncate text-[12.5px] font-medium md:inline">
              {user?.username || '我的账号'}
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
            {user?.username || '我的账号'}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => { void navigate('/settings/bindings') }}>账号绑定</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={() => setLogoutOpen(true)}>
            <LogOut className="h-3.5 w-3.5" />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 全局检索（⌘K） */}
      <GlobalSearch
        open={searchOpen}
        onOpenChange={setSearchOpen}
        onPickUnavailable={(label) => notify(`${label}详情页正在开发中`)}
      />

      {/* 退出确认：破坏性操作，明确告知后果再执行 */}
      <Dialog open={logoutOpen} onOpenChange={setLogoutOpen}>
        <DialogContent className="max-w-[360px]">
          <DialogHeader>
            <DialogTitle>确认退出登录？</DialogTitle>
            <DialogDescription>退出后需要重新输入账号密码。当前未保存的编辑会丢失。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLogoutOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleLogout}>
              退出登录
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
