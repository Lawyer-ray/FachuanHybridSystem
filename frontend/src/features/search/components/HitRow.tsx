import { Link } from 'react-router'

import { BADGE_TONE_CLS } from '@/components/shared/StatusBadge'
import { cn } from '@/lib/utils'

import { SIDE_LABEL, type CategoryMeta } from '../categories'
import type { Hit } from '../types'
import { PANEL_BADGE_CLS } from './ProjectHits'

/**
 * 平铺类别（当事人 / 收件箱 / 法院短信 / 联系人）的一行命中。
 *
 * 两种形态，取决于该类**是否已有详情页**：
 * - 有（`to` 非空）：渲染 `<Link>`，鼠标点与键盘回车走同一跳转；
 * - 没有：渲染 `<button>`，点后由调用方提示「还没做」，并挂一枚「未建页」标签。
 *
 * 抽出来的原因：这层「有无去处 → 换元素类型」的分支连同行内三件套（图标 +
 * 标题 + 侧别/副标题）原先内联在结果区的 map 里，与分组、光标序、筛选混在
 * 一起看；行本身只吃一条命中 + 一个 active 标记。
 */
export function HitRow({
  hit,
  category,
  to,
  active,
  onOpenChange,
  onPick,
}: {
  hit: Hit
  /** 类别注册表项：图标 + 未建页时的提示名（见 ../categories） */
  category: CategoryMeta
  /** 该类的站内路径；undefined = 还没建页，走按钮形态 */
  to: string | undefined
  /** 键盘光标是否落在这一行 */
  active: boolean
  onOpenChange: (v: boolean) => void
  onPick: (hit: Hit) => void
}) {
  const Icon = category.icon
  const content = (
    <>
      <Icon className="h-3.5 w-3.5 flex-none text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate text-[12.5px]">{hit.title}</span>
      {hit.side && <SideBadge side={hit.side} />}
      {hit.subtitle && (
        <span className="max-w-[140px] flex-none truncate text-[10.5px] text-muted-foreground">{hit.subtitle}</span>
      )}
    </>
  )

  if (to) {
    return (
      <Link
        to={to}
        onClick={() => onOpenChange(false)}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-[7px] px-2 py-[7px] no-underline transition-colors',
          active ? 'bg-secondary text-foreground' : 'text-secondary-foreground hover:bg-secondary/60',
        )}
      >
        {content}
      </Link>
    )
  }

  return (
    <button
      type="button"
      onClick={() => onPick(hit)}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-[7px] px-2 py-[7px] text-left text-secondary-foreground transition-colors',
        active ? 'bg-secondary' : 'hover:bg-secondary/60',
      )}
    >
      {content}
      <span className="flex-none text-[10px] text-muted-foreground">未建页</span>
    </button>
  )
}

/**
 * 当事人我方/对方徽章：我方实底、对方描边——同一面板里筛选标签已用「实底=选中 /
 * 描边=未选」这套视觉词汇，复用它让「我方」一眼跳出来，又不引入新颜色。
 * 形状取 ProjectHits 的 PANEL_BADGE_CLS，描边色取 BADGE_TONE_CLS.neutral（与「非诉」同款）。
 */
function SideBadge({ side }: { side: 'ours' | 'opposing' }) {
  return (
    <span
      className={cn(
        PANEL_BADGE_CLS,
        side === 'ours' ? 'bg-foreground text-background' : BADGE_TONE_CLS.neutral,
      )}
    >
      {SIDE_LABEL[side]}
    </span>
  )
}
