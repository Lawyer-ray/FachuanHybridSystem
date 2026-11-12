/**
 * 回扫 —— 「已自动认领并归案」卡片：筛选条 + 邮件行 + 空态。
 *
 * 一屏要回答「哪些归上了、哪些没归上」，所以状态筛选条与列表放在同一个组件里：
 * 筛选口径是这一块自己的视图状态，不外泄给面板。
 * 行点击开邮件抽屉、行内「指定归属」走归案向导，两者都是页面级抽屉，
 * 因此只向上回调 `onOpenMail` / `onAssign`。
 */
import { CheckCircle2, HelpCircle, Inbox, Search } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/lib/utils'
import { DEMO_RETURNED_MAILS, DEMO_X2_CLAIM_FILTERS, type ClaimFilter } from '../../demo-data'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../../ui'
import { claimKindOf } from './claim-kind'

/** 归案结果列表（含筛选条） */
export function ClaimedMailCard({
  /* 演示：标记为无关的邮件，行上的「处理结果」跟着翻成「已标记无关」 */
  ignored,
  onOpenMail,
  onAssign,
}: {
  ignored: Set<string>
  onOpenMail: (subject: string) => void
  onAssign: (subject: string) => void
}) {
  /** 归案日志筛选 */
  const [claimFilter, setClaimFilter] = useState<ClaimFilter>('全部')

  const rows = DEMO_RETURNED_MAILS.map((m) => (ignored.has(m.subject) ? { ...m, action: '已标记无关' } : m))
  const ignoredCount = rows.filter((m) => claimKindOf(m.action) === 'ignored').length

  const claimCount = (f: ClaimFilter) =>
    f === '全部'
      ? rows.length
      : rows.filter((m) => claimKindOf(m.action) === (f === '自动归案' ? 'auto' : f === '待人工' ? 'manual' : 'ignored')).length
  const shownMails =
    claimFilter === '全部'
      ? rows
      : rows.filter(
          (m) => claimKindOf(m.action) === (claimFilter === '自动归案' ? 'auto' : claimFilter === '待人工' ? 'manual' : 'ignored'),
        )

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <Inbox className="size-3.5 flex-none text-muted-foreground" />
        <SectionTitle title="已自动认领并归案" hint="按案号 / 当事人名 / 文件名关键词匹配" className="w-full" />
      </div>

      {/* 归案状态筛选 */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border-light bg-secondary/25 px-5 py-2">
        <span className="text-[10.5px] text-muted-foreground">筛选</span>
        {DEMO_X2_CLAIM_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={claimFilter === f}
            onClick={() => setClaimFilter(f)}
            className={cn(
              'h-[24px] rounded-[6px] border px-2 text-[11px] transition-colors',
              claimFilter === f
                ? 'border-foreground bg-foreground font-semibold text-background'
                : 'border-border bg-card font-[550] text-secondary-foreground hover:bg-secondary',
            )}
          >
            {f}
            <span className={cn('ml-1 tabular-nums', claimFilter === f ? 'opacity-70' : 'text-muted-foreground')}>
              {claimCount(f)}
            </span>
          </button>
        ))}
        {ignoredCount > 0 ? (
          <span className="ml-auto text-[10px] text-muted-foreground">已标记无关 {ignoredCount} 封</span>
        ) : null}
      </div>

      <ul className="divide-y divide-border-light">
        {shownMails.map((m) => {
          const kind = claimKindOf(m.action)
          const isAuto = kind === 'auto'
          return (
            <li
              key={m.subject}
              onClick={() => onOpenMail(m.subject)}
              className="flex cursor-pointer items-start gap-3 px-5 py-3 transition-colors hover:bg-secondary/40"
            >
              <span
                className={cn(
                  'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                  isAuto ? 'bg-status-green' : kind === 'ignored' ? 'bg-secondary' : 'bg-status-yellow',
                )}
              >
                {isAuto ? (
                  <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                ) : (
                  <HelpCircle className={cn('size-2.5', kind === 'ignored' ? 'text-muted-foreground' : 'text-white')} strokeWidth={3} />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-medium" title={m.subject}>
                  {m.subject}
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                  <span>{m.from}</span>
                  <span className="text-border">·</span>
                  <span>{m.attachments} 个附件</span>
                  <span className="text-border">·</span>
                  <span>匹配依据：{m.matchedBy}</span>
                </div>
                <div
                  className={cn(
                    'mt-1 text-[10.5px]',
                    isAuto ? 'text-status-green' : kind === 'ignored' ? 'text-muted-foreground' : 'text-status-yellow',
                  )}
                >
                  {m.action}
                </div>
              </div>
              <div className="flex flex-none flex-col items-end gap-1">
                <Pill tone={isAuto ? 'green' : kind === 'ignored' ? 'neutral' : 'yellow'}>{m.matchedCase}</Pill>
                <span className="text-[10px] tabular-nums text-muted-foreground">{m.at}</span>
                {kind === 'manual' ? (
                  /* 行本身是「打开邮件抽屉」，这里要拦住冒泡，只开归案弹窗 */
                  <span onClick={(e) => e.stopPropagation()}>
                    <ActionButton sm onClick={() => onAssign(m.subject)}>
                      <Search className="size-3" />
                      指定归属
                    </ActionButton>
                  </span>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
      {shownMails.length === 0 ? (
        <div className="px-5 py-6 text-center text-[11.5px] text-muted-foreground">
          「{claimFilter}」下没有邮件
        </div>
      ) : null}
    </WorkCard>
  )
}
