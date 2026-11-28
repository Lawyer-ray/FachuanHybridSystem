import { LogOut, MoreHorizontal, Plus, Search, Settings } from 'lucide-react'

import { cn } from '@/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/**
 * 手机端「…」溢出菜单（AppNavbar 专用）。
 *
 * 为什么抽成同目录子组件：AppNavbar 已到 335 行（软红线 350），而这张分组表
 * 本身就要一百来行（三组小标题、组间分隔线、44px 触控高度、每条目的可访问
 * 名）。留在 AppNavbar 里会把「壳层导航为什么长这样」的历史注释挤没。
 *
 * 手机端导航栏右侧原本平铺四个动作（AI 助手 / 全局检索 / 新建项目 / 用户菜单），
 * 360px 上排不下，且次要动作常驻反而稀释了主操作。现在收敛成这一个「…」，
 * 按 导航 / 动作 / 账户 分组收进浮层——注意 AI 助手的手机入口不在这里，而是
 * AppShell 底部那枚 composer 形状的 pill（拇指够得到）。
 *
 * ⚠️ 所有条目的可访问名都带「（菜单）」后缀：桌面按钮（全局检索 / 新建项目 /
 * 用户菜单）与 ☰ 的三个导航链接在 DOM 里始终存在，只是被媒体查询隐藏，而
 * jsdom 不跑媒体查询——同名会让 `getByRole` 一次命中两个（同 AppShell 底部
 * pill 注释里的那次教训）。桌面上看不到这张表，后缀只影响读屏与测试。
 */

export interface NavbarNavItem {
  to: string
  label: string
  active: boolean
}

export interface NavbarMobileMenuProps {
  /** 导航条目（与桌面 <nav> 共用同一份定义，见 AppNavbar 的 navItems） */
  navItems: NavbarNavItem[]
  /** 站内跳转（含乐观高亮；调用方负责关掉 ☰ 面板） */
  onNavigate: (to: string) => void
  /** 悬停 / 聚焦条目时预取目标页 chunk */
  onPrefetch?: (to: string) => void
  onOpenSearch: () => void
  onOpenNewProject: () => void
  onOpenSettings: () => void
  /** 打开现有的退出确认弹窗（不能点一下直接登出） */
  onOpenLogout: () => void
}

/** 分组小标题：比菜单项低一档的字号 + 弱化色，起「分隔章节」而不是「一条命令」的作用 */
const GROUP_LABEL = 'px-3 pt-2 pb-1 text-[11px] text-muted-foreground'
/** 触控目标 ≥44px（min-h-11）：手机上没有 hover，条目太窄会连点错 */
const MENU_ITEM = 'min-h-11 gap-2.5 px-3 text-[13px]'
/** 组间分隔：一条 border-t 细线（h-0 抵掉 Separator 自带的 h-px，避免 2px 粗线） */
const GROUP_DIVIDER = 'my-1 h-0 border-t border-border bg-transparent'

export function NavbarMobileMenu({
  navItems,
  onNavigate,
  onPrefetch,
  onOpenSearch,
  onOpenNewProject,
  onOpenSettings,
  onOpenLogout,
}: NavbarMobileMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="更多操作"
          title="更多"
          className="hidden h-8 w-8 flex-none items-center justify-center rounded-[8px] text-foreground max-[760px]:flex"
        >
          <MoreHorizontal className="h-[18px] w-[18px]" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={6} className="w-60 rounded-xl p-1.5">
        <DropdownMenuLabel className={GROUP_LABEL}>导航</DropdownMenuLabel>
        {navItems.map((item) => (
          <DropdownMenuItem
            key={item.to}
            aria-label={`${item.label}（菜单）`}
            className={cn(MENU_ITEM, item.active && 'bg-secondary text-foreground')}
            onSelect={() => onNavigate(item.to)}
            onPointerEnter={() => onPrefetch?.(item.to)}
            onFocus={() => onPrefetch?.(item.to)}
          >
            {item.label}
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator className={GROUP_DIVIDER} />
        <DropdownMenuLabel className={GROUP_LABEL}>动作</DropdownMenuLabel>
        <DropdownMenuItem
          aria-label="新建项目（菜单）"
          className={MENU_ITEM}
          onSelect={onOpenNewProject}
        >
          <Plus className="size-4" />
          新建项目
        </DropdownMenuItem>
        {/* ⌘K 在触屏上不存在：这里是手机打开全局检索的唯一入口，别删 */}
        <DropdownMenuItem
          aria-label="全局检索（菜单）"
          className={MENU_ITEM}
          onSelect={onOpenSearch}
        >
          <Search className="size-4" />
          全局检索
        </DropdownMenuItem>

        <DropdownMenuSeparator className={GROUP_DIVIDER} />
        <DropdownMenuLabel className={GROUP_LABEL}>账户</DropdownMenuLabel>
        <DropdownMenuItem aria-label="设置（菜单）" className={MENU_ITEM} onSelect={onOpenSettings}>
          <Settings className="size-4" />
          设置
        </DropdownMenuItem>
        <DropdownMenuItem
          aria-label="退出登录（菜单）"
          variant="destructive"
          className={MENU_ITEM}
          onSelect={onOpenLogout}
        >
          <LogOut className="size-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
