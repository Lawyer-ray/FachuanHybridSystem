import { startTransition, useEffect, useOptimistic, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LogOut, Menu, Plus, Search, Sparkles, User } from 'lucide-react'

import { useAuth, type User as AuthUser } from '@/features/auth'
import { api } from '@/lib/api'
import { resetAllClientState } from '@/lib/reset-client-state'
import { Button } from '@/components/ui/button'
import { BrandMark } from '@/components/shared/BrandMark'
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
 * 全局顶层导航（全站唯一一套，由 App 的 AppShell 渲染一次、跨页面常驻）。
 *
 * 合并自原「首页 TopNav」与「材料预处理页内联 header」：此前两处各写一份，
 * 跨页面跳转时导航会变形（一边有 logo + 退出，一边没有）。按 frontend/CLAUDE.md
 * 的提权规则，navbar 被 ≥2 个 feature 使用，故收敛到 components/shared/。
 * 后来又从各页面内部提到壳层：页面各自渲染一份时，切换路由会把导航栏连同
 * 页面一起卸载重挂，未缓存的页面 chunk 加载期间导航栏直接消失（闪烁源头）。
 */
export interface AppNavbarProps {
  /** 未实现入口的回调（给 toast 提示） */
  onNotify?: (msg: string) => void
  /** 退出登录后跳转；不传则默认回 /login */
  onLogout?: () => void
  /** 导航入口悬停 / 聚焦时预取该路由的页面 chunk（AppShell 注入；须幂等） */
  onPrefetch?: (to: string) => void
  /** 切换右侧 AI 助手面板（AppShell 注入，展开状态由壳层持久化） */
  onToggleCopilot?: () => void
  /** 全局检索面板开关（AppShell 注入：⌘K 快捷键与 AI 助手面板的互斥联动都在壳层） */
  searchOpen: boolean
  onSearchOpenChange: (v: boolean) => void
}

/** 补拉当前用户信息的 query key（本组件独用，就地定义） */
const ORG_ME_KEY = ['organization-me'] as const

/** 与 react-router Link 相同的判定：只有不带修饰键的左键点击才会站内导航 */
function isPlainLeftClick(e: React.MouseEvent): boolean {
  return e.button === 0 && !e.metaKey && !e.altKey && !e.ctrlKey && !e.shiftKey
}

export function AppNavbar({
  onNotify,
  onLogout,
  onPrefetch,
  onToggleCopilot,
  searchOpen,
  onSearchOpenChange,
}: AppNavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)
  const { pathname } = useLocation()
  // 点击导航后、目标页面 chunk 到达前，react-router 的导航 transition 尚未提交，
  // pathname 还停在旧值（React 保住旧页面不退回 fallback）。useOptimistic 让
  // 被点的标签在这段时间里先行高亮给即时反馈；transition 提交后自动回落到
  // 真实 pathname，此时二者相同，没有跳变。
  const [navPath, setNavPath] = useOptimistic(pathname)
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
  // 整个 me 透传（含 real_name/avatar_url，头像位消费）；enabled 仍由
  // user.username 翻转控制，回写后 query 转禁用、data 保留，effect 不再触发。
  useEffect(() => {
    const me = meQuery.data
    if (me?.username) setUser(me)
  }, [meQuery.data, setUser])

  const notify = (msg: string) => onNotify?.(msg)

  /** 导航入口点击：自己接管站内导航，好把乐观高亮与路由更新放进同一个 transition */
  const selectNav = (to: string, e: React.MouseEvent<HTMLAnchorElement>) => {
    setMenuOpen(false)
    // 带修饰键 / 非左键：Link 本身也不会站内导航（交给浏览器开新标签等），不抢先高亮
    if (e.defaultPrevented || !isPlainLeftClick(e)) return
    e.preventDefault()
    startTransition(() => {
      setNavPath(to)
      // 同 Link：重复点当前页用 replace，不堆历史记录
      void navigate(to, { replace: to === pathname })
    })
  }

  // 检索面板开关（⌘K）与 AI 助手面板（⌘J）的互斥、快捷键监听都在 AppShell 壳层：
  // 两层浮层的状态必须同层协调，否则同屏叠加。这里只消费注入的开关。

  const handleLogout = () => {
    setLogoutOpen(false)
    // 清 auth store 的 user（resetAllClientState 只负责 token 与各 feature 状态）
    logout()
    // 与「会话过期被踢」共用同一条清理路径（resetAllClientState）：此前两条
    // 路径清理范围不一致，过期跳转只清 token，换人登录会读到上一账号的
    // 材料草稿等 localStorage 残留
    void resetAllClientState(() => queryClient.clear())
    // react-router 的 navigate 返回 void | Promise<void>，这里 fire-and-forget
    void navigate('/login', { replace: true })
    onLogout?.()
  }

  return (
    <header className="sticky top-0 z-50 flex h-(--app-navbar-h) items-center gap-2 border-b border-border bg-card/80 px-[22px] backdrop-blur-[14px]">
      <button
        type="button"
        className="hidden h-8 w-8 items-center justify-center rounded-[8px] text-foreground max-[760px]:flex"
        onClick={() => setMenuOpen((v) => !v)}
        aria-label="菜单"
      >
        <Menu className="h-[18px] w-[18px]" />
      </button>

      {/* 品牌：产品名（点击回首页）。字标统一由 BrandMark 出，客户上传页也用它，
          保证对外门面与登录后的观感一致 */}
      <Link to="/" className="flex flex-none items-center pr-1.5 no-underline">
        <BrandMark />
      </Link>

      <nav
        className={`items-center gap-[2px] max-[760px]:fixed max-[760px]:inset-x-0 max-[760px]:top-(--app-navbar-h) max-[760px]:z-49 max-[760px]:flex-col max-[760px]:items-stretch max-[760px]:border-b max-[760px]:border-border max-[760px]:bg-card max-[760px]:p-2 max-[760px]:shadow-[0_12px_24px_rgba(0,0,0,.08)] ${
          menuOpen ? 'flex' : 'max-[760px]:hidden'
        } md:flex`}
      >
        <NavLink to="/" label="首页" active={navPath === '/'} onSelect={selectNav} onPrefetch={onPrefetch} />
        {/* 「收件箱」与「材料预处理」已合并为一个入口：它们是同一条流水线的前后两段
            （收件箱 → 拆包 → 归案），并排两个按钮看不出先后关系。现在阶段在页内切换，
            navPath 同时覆盖 /inbox 这个旧前缀，让前转期间不会两个入口都不高亮。 */}
        <NavLink
          to="/material-prep"
          label="预处理"
          active={navPath.startsWith('/material-prep') || navPath.startsWith('/inbox')}
          onSelect={selectNav}
          onPrefetch={onPrefetch}
        />
        <NavLink
          to="/projects"
          label="办案"
          active={navPath.startsWith('/projects')}
          onSelect={selectNav}
          onPrefetch={onPrefetch}
        />
      </nav>

      {/* AI 助手：右侧常驻对话面板（features/copilot，壳层懒加载）。
          ml-auto 由它承担右推；未传回调时（单测等场景）仍由检索按钮承担 */}
      {onToggleCopilot && (
        <button
          type="button"
          className="ml-auto hidden h-8 items-center gap-[7px] rounded-[8px] border border-border bg-secondary px-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-input hover:bg-card sm:flex"
          onClick={onToggleCopilot}
        >
          <Sparkles className="h-[13px] w-[13px]" />
          <span>AI 助手</span>
          <kbd className="rounded-[4px] border border-input bg-card px-[5px] py-[1px] text-[10px] text-muted-foreground">⌘J</kbd>
        </button>
      )}

      {/* 全局检索 */}
      <button
        type="button"
        className={`${onToggleCopilot ? '' : 'ml-auto '}hidden h-8 items-center gap-[7px] rounded-[8px] border border-border bg-secondary px-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-input hover:bg-card sm:flex`}
        onClick={() => onSearchOpenChange(true)}
      >
        <Search className="h-[13px] w-[13px]" />
        <span>检索</span>
        <kbd className="rounded-[4px] border border-input bg-card px-[5px] py-[1px] text-[10px] text-muted-foreground">⌘K</kbd>
      </button>

      <button
        type="button"
        className="flex h-8 items-center gap-1.5 rounded-[8px] bg-foreground px-3.5 text-[12.5px] font-semibold whitespace-nowrap text-background transition-opacity hover:opacity-85"
        onClick={() => notify('新建项目：可先把材料上传到「材料预处理」归案')}
      >
        <Plus className="h-3 w-3" strokeWidth={2.5} />
        新建项目
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
          <DropdownMenuItem onClick={() => { void navigate('/settings') }}>设置</DropdownMenuItem>
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
        onOpenChange={onSearchOpenChange}
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
  onSelect,
  onPrefetch,
}: {
  to: string
  label: string
  active: boolean
  onSelect: (to: string, e: React.MouseEvent<HTMLAnchorElement>) => void
  onPrefetch?: (to: string) => void
}) {
  // 鼠标悬停 / 键盘聚焦 / 触屏按下即预取目标页 chunk：从意图到点击的间隙通常够把
  // 小 chunk 拉完，点下去就是即时切换
  const prefetch = () => onPrefetch?.(to)
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      onClick={(e) => onSelect(to, e)}
      onMouseEnter={prefetch}
      onFocus={prefetch}
      onTouchStart={prefetch}
      className={`cursor-pointer rounded-[8px] px-3 py-[7px] text-[13.5px] font-medium whitespace-nowrap no-underline transition-colors hover:bg-secondary hover:text-foreground ${
        active ? 'bg-secondary text-foreground' : 'text-secondary-foreground'
      }`}
    >
      {label}
    </Link>
  )
}
