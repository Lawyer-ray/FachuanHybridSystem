import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { Menu, Plus, Search } from 'lucide-react'

import { NAV_ITEMS } from '../constants'
import { useAuth } from '@/features/auth/store'

/**
 * 首页顶层导航（原型 .navbar）：品牌 + 主导航 + 全局检索 + 新建案件 + 头像。
 * 只链接已真实存在的页面；未实现的入口给明确 toast，不做成假路由。
 */
export function TopNav({ onNotify }: { onNotify: (msg: string) => void }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const user = useAuth((s) => s.user)

  const initial = (user?.username || '我').trim().slice(0, 1) || '我'

  return (
    <header className="sticky top-0 z-50 flex h-[54px] items-center gap-2 border-b border-border bg-card/80 px-[22px] backdrop-blur-[14px]">
      <button
        type="button"
        className="hidden max-[760px]:flex h-8 w-8 items-center justify-center rounded-[8px] text-foreground"
        onClick={() => setOpen((v) => !v)}
        aria-label="菜单"
      >
        <Menu className="h-[18px] w-[18px]" />
      </button>

      <div className="flex items-center gap-[9px] pr-1.5">
        <div className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] bg-foreground text-[13px] font-bold text-background">
          法
        </div>
        <div className="text-[14px] font-bold whitespace-nowrap tracking-[-0.01em]">
          法穿 <span className="text-[12.5px] font-medium text-muted-foreground">AI Copilot</span>
        </div>
      </div>

      <nav
        className={`items-center gap-[2px] max-[760px]:fixed max-[760px]:inset-x-0 max-[760px]:top-[54px] max-[760px]:z-49 max-[760px]:flex-col max-[760px]:items-stretch max-[760px]:border-b max-[760px]:border-border max-[760px]:bg-card max-[760px]:p-2 max-[760px]:shadow-[0_12px_24px_rgba(0,0,0,.08)] ${
          open ? 'flex' : 'max-[760px]:hidden'
        } md:flex`}
      >
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`cursor-pointer rounded-[8px] px-3 py-[7px] text-[13.5px] font-medium whitespace-nowrap no-underline transition-colors hover:bg-secondary hover:text-foreground ${
              pathname === item.to ? 'bg-secondary text-foreground' : 'text-secondary-foreground'
            }`}
          >
            {item.label}
          </Link>
        ))}
        <button
          type="button"
          className="cursor-pointer rounded-[8px] px-3 py-[7px] text-left text-[13.5px] font-medium whitespace-nowrap text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => onNotify('办案工作台正在开发中')}
        >
          办案
        </button>
        <button
          type="button"
          className="cursor-pointer rounded-[8px] px-3 py-[7px] text-left text-[13.5px] font-medium whitespace-nowrap text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => onNotify('案件台账正在开发中')}
        >
          台账
        </button>
      </nav>

      <button
        type="button"
        className="ml-auto hidden h-8 items-center gap-[7px] rounded-[8px] border border-border bg-secondary px-2.5 text-[12.5px] text-muted-foreground transition-colors hover:border-input hover:bg-card sm:flex"
        onClick={() => onNotify('全局检索（跨案件 / 材料 / 当事人）正在开发中')}
      >
        <Search className="h-[13px] w-[13px]" />
        <span>检索</span>
        <kbd className="rounded-[4px] border border-input bg-card px-[5px] py-[1px] text-[10px] text-muted-foreground">⌘K</kbd>
      </button>

      <button
        type="button"
        className="flex h-8 items-center gap-1.5 rounded-[8px] bg-foreground px-3.5 text-[12.5px] font-semibold whitespace-nowrap text-background transition-opacity hover:opacity-85"
        onClick={() => onNotify('新建案件：可先把材料上传到「材料预处理」归案')}
      >
        <Plus className="h-3 w-3" strokeWidth={2.5} />
        新建案件
      </button>

      <div
        className="ml-1 flex h-7 w-7 flex-none cursor-pointer items-center justify-center rounded-full bg-foreground text-[11px] font-semibold text-background"
        title={user?.username || '个人中心'}
        onClick={() => onNotify('个人中心正在开发中')}
      >
        {initial}
      </div>
    </header>
  )
}
