/**
 * ③ 缺件 —— 逐项缺件清单（可勾选、点开看完整沟通）。
 *
 * 一行一件：勾选框 + 状态圆点 + 缺件名/来源/等级/原因 + 右侧渠道与状态。
 * 勾选框 stopPropagation，避免勾选同时把详情抽屉打开。
 */
import { AlertTriangle, CheckCircle2, CheckSquare, Clock, FileText, Mail, MessageSquare, Square } from 'lucide-react'

import { DEMO_GAP_NOTICES, DEMO_X2_GAP_TIMELINE, type GapNoticeRow } from '../../demo-data'
import { Pill } from '../../ui'
import { cn } from '@/lib/utils'

import { sourceOf } from './gap-utils'

/** 通知渠道图标（未知渠道退化为邮件） */
const CHANNEL_ICON: Record<string, typeof Mail> = {
  '短信 + 邮件': Mail,
  微信: MessageSquare,
  邮件: Mail,
}

/** 缺件清单：一行一件 */
export function GapNoticeList({
  visible,
  checked,
  onToggle,
  onPick,
}: {
  visible: GapNoticeRow[]
  checked: Set<string>
  onToggle: (item: string) => void
  onPick: (item: string) => void
}) {
  return (
    <ul className="divide-y divide-border-light">
      {visible.map((g) => {
        const Icon = CHANNEL_ICON[g.channel] ?? Mail
        const done = g.status === 'received'
        const isChecked = checked.has(g.item)
        const timelineCount = DEMO_X2_GAP_TIMELINE.filter((t) => t.item === g.item).length
        return (
          <li
            key={g.item}
            onClick={() => onPick(g.item)}
            className={cn(
              'flex cursor-pointer items-start gap-2.5 px-5 py-3 transition-colors hover:bg-secondary/40',
              isChecked && 'bg-secondary/50',
            )}
          >
            <button
              type="button"
              aria-label={`勾选 ${g.item}`}
              aria-pressed={isChecked}
              onClick={(e) => {
                e.stopPropagation()
                onToggle(g.item)
              }}
              className="mt-[2px] flex-none text-muted-foreground hover:text-foreground"
            >
              {isChecked ? <CheckSquare className="size-3.5 text-foreground" /> : <Square className="size-3.5" />}
            </button>

            <span
              className={cn(
                'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                done ? 'bg-status-green' : g.severity === 'blocker' ? 'bg-status-red' : 'bg-status-yellow',
              )}
            >
              {done ? (
                <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
              ) : g.severity === 'blocker' ? (
                <AlertTriangle className="size-2.5 text-white" strokeWidth={3} />
              ) : (
                <Clock className="size-2.5 text-white" strokeWidth={3} />
              )}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[12.5px] font-medium">{g.item}</span>
                <span className="rounded-[4px] border border-border-light bg-background px-1 text-[9.5px] text-muted-foreground">
                  {sourceOf(g.item)}
                </span>
                {g.severity === 'blocker' ? (
                  <span className="text-[9.5px] font-semibold text-status-red">硬阻塞</span>
                ) : null}
              </div>
              <div className="mt-0.5 text-[10.5px] leading-[1.55] text-muted-foreground">{g.reason}</div>
              {done ? (
                <div className="mt-1 flex items-center gap-1.5 text-[10.5px] text-status-green">
                  <CheckCircle2 className="size-2.5" />
                  {g.reply}
                </div>
              ) : null}
              <div className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
                <FileText className="size-2.5" />
                {timelineCount} 条往来记录 · 点开看完整沟通
              </div>
            </div>

            <div className="flex flex-none flex-col items-end gap-1">
              <div className="flex items-center gap-1 text-[10.5px] text-muted-foreground">
                <Icon className="size-2.5" />
                {g.channel}
              </div>
              <span className="text-[10px] tabular-nums text-muted-foreground">{g.sentAt}</span>
              <Pill tone={done ? 'green' : g.status === 'pending' ? 'yellow' : 'red'}>
                {done ? '已补齐' : g.status === 'pending' ? '已发出' : '等待客户'}
              </Pill>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** 当前分组下没有缺件时的占位 */
export function GapNoticeEmpty({ tabLabel }: { tabLabel: string }) {
  return (
    <div className="px-5 py-6 text-center text-[11.5px] text-muted-foreground">「{tabLabel}」下没有待补材料</div>
  )
}

/** 清单卡头的条数提示：「全部」显示总数，分组显示 命中 / 总数 */
export function GapNoticeCount({ tab, visibleCount }: { tab: string; visibleCount: number }) {
  return (
    <span className="text-[10.5px] tabular-nums text-muted-foreground">
      {tab === '全部' ? `${DEMO_GAP_NOTICES.length} 项` : `${visibleCount} / ${DEMO_GAP_NOTICES.length} 项`}
    </span>
  )
}
