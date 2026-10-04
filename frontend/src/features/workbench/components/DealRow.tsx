import { ArrowRight, Eye } from 'lucide-react'

import { relDue } from '../domain'
import type { WorkbenchDeal } from '../types'

interface DealRowProps {
  deal: WorkbenchDeal
  /** 右键行 / 👁 按钮：打开详情抽屉 */
  onOpenSheet: (deal: WorkbenchDeal) => void
  /** 左键行 / → 按钮：详情页（开发中，仅提示） */
  onDetailNotReady: () => void
}

/**
 * 列表行：名称主视觉 + 我方 vs 对方副行 + 金额/到期右对齐。
 * 交互语义：左键 = 详情（开发中）、右键/👁 = 抽屉预览。
 */
export function DealRow({ deal, onOpenSheet, onDetailNotReady }: DealRowProps) {
  const today = deal.daysLeft === 0
  return (
    <div
      data-deal-id={deal.id}
      role="button"
      tabIndex={0}
      className={
        'group flex cursor-pointer items-center gap-[18px] border-b border-border px-4 py-3 transition-colors last:border-b-0 hover:bg-secondary active:bg-secondary ' +
        (today ? 'today' : '')
      }
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('[data-prev]')) return
        onDetailNotReady()
      }}
      onKeyDown={(e) => {
        // 键盘可达：Enter / Space 等价左键行（详情占位）；右键抽屉无键盘等价，走 👁 按钮
        if (e.key !== 'Enter' && e.key !== ' ') return
        // 行内按钮自身可激活：按键交给按钮，不重复触发行级动作
        if ((e.target as HTMLElement).closest('button')) return
        e.preventDefault()
        onDetailNotReady()
      }}
      onContextMenu={(e) => {
        e.preventDefault()
        onOpenSheet(deal)
      }}
    >
      {/* 状态点：今日到期红点脉冲，其余灰点 */}
      <span className="relative flex size-[7px] flex-none items-center justify-center">
        {today ? (
          <>
            <span className="absolute size-[7px] animate-ping rounded-full bg-status-red/40" />
            <span className="size-[7px] rounded-full bg-status-red" />
          </>
        ) : (
          <span className="size-[7px] rounded-full bg-border" />
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div
          title={deal.client}
          className={
            'line-clamp-2 text-[14.5px] leading-[1.45] font-[570] tracking-[-0.006em] break-all text-secondary-foreground transition-colors group-hover:text-foreground ' +
            (today ? 'text-foreground' : '')
          }
        >
          {deal.client}
        </div>
        <div className="mt-[3px] flex items-center gap-2 overflow-hidden text-[11.5px] whitespace-nowrap text-muted-foreground">
          <span className="truncate">
            {deal.parties.client}
            {deal.parties.other && (
              <>
                <span className="mx-1.5 text-[10px] text-border">vs</span>
                {deal.parties.other}
              </>
            )}
          </span>
          {deal.no && <span className="flex-none text-muted-foreground/70 tabular-nums">{deal.no}</span>}
        </div>
      </div>

      <div className="flex flex-none flex-col items-end gap-0.5 text-right">
        {deal.amount && <div className="text-[14px] font-[620] tracking-[-0.01em] tabular-nums">{deal.amount}</div>}
        {deal.daysLeft != null && (
          <div className={'text-[11px] tabular-nums ' + (today ? 'font-[650] text-status-red' : 'text-muted-foreground')}>
            {relDue(deal.daysLeft)}
          </div>
        )}
      </div>

      <div className="flex flex-none gap-[5px]">
        <button
          type="button"
          data-prev
          title="快速预览（右键行同效）"
          aria-label="快速预览"
          className="flex size-[27px] items-center justify-center rounded-[8px] text-muted-foreground/70 opacity-40 transition-all hover:bg-foreground hover:text-background hover:opacity-100 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation()
            onOpenSheet(deal)
          }}
        >
          <Eye className="size-[14px]" />
        </button>
        <button
          type="button"
          title="打开详情（开发中）"
          aria-label="打开详情"
          className="flex size-[27px] items-center justify-center rounded-[8px] text-muted-foreground/70 opacity-40 transition-all hover:bg-foreground hover:text-background hover:opacity-100 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation()
            onDetailNotReady()
          }}
        >
          <ArrowRight className="size-[14px]" />
        </button>
      </div>
    </div>
  )
}
