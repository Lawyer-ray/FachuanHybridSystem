/**
 * 修订清单：审查维度筛选 + 逐条展开 + 对方律师意见
 *
 * 顶部 tab 是律师看审查意见时的第一动作——「先看高风险的」「只看挂了法条的」
 * 「只看要我拍板的」。tab 的计数与过滤结果同源（见 crossborder-domain），
 * 不会出现「高 2」却列出 3 条的情况。
 */

import { ChevronDown, MessageSquareQuote } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  DEMO_NL2_COUNTER_OPINIONS,
  DEMO_NL2_FILTERS,
  DEMO_TH_CONTRACT_REVISIONS,
  type DemoContractRevision,
} from '../../demo-nonlit'
import { Card } from '../../ui'
import { TonePill as Pill } from './crossborder-ui'
import { filterRevisions, filterTabLabel } from './crossborder-domain'

const SEV_TONE = { high: 'red', mid: 'yellow', low: 'neutral' } as const
const SEV_TEXT = { high: '高', mid: '中', low: '低' } as const
const ATTITUDE_TONE = { 接受: 'green', 还价: 'yellow', 拒绝: 'red' } as const

export function RevisionBoard({
  tabId,
  onPickTab,
  picked,
  onPick,
}: {
  tabId: string
  onPickTab: (id: string) => void
  /** 展开的那一条（与双语视图共享，点清单即联动高亮） */
  picked: string | null
  onPick: (id: string | null) => void
}) {
  const tab = DEMO_NL2_FILTERS.find((t) => t.id === tabId) ?? DEMO_NL2_FILTERS[0]!
  const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, tab)

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">修订清单</h3>
        <span className="text-[11px] text-muted-foreground">按维度筛 · 点开看原文、改法与法条依据</span>
      </div>

      {/* 审查维度 tabs */}
      <div className="mt-2.5 flex flex-wrap gap-1">
        {DEMO_NL2_FILTERS.map((t) => {
          const on = t.id === tab.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onPickTab(t.id)}
              className={cn(
                'inline-flex h-[26px] items-center rounded-[7px] border px-2.5 text-[11.5px] whitespace-nowrap transition-colors',
                on
                  ? 'border-foreground bg-foreground font-semibold text-background'
                  : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
              )}
            >
              {filterTabLabel(t, DEMO_TH_CONTRACT_REVISIONS.length)}
            </button>
          )
        })}
      </div>

      <div className="mt-2.5 flex flex-col gap-1.5">
        {rows.length === 0 ? (
          <div className="rounded-[9px] border border-dashed border-border px-3 py-3 text-center text-[11px] text-muted-foreground">
            该维度下没有修订。
          </div>
        ) : null}
        {rows.map((r) => (
          <RevisionRow
            key={r.id}
            rev={r}
            open={picked === r.id}
            onToggle={() => onPick(picked === r.id ? null : r.id)}
          />
        ))}
      </div>
    </Card>
  )
}

function RevisionRow({ rev, open, onToggle }: { rev: DemoContractRevision; open: boolean; onToggle: () => void }) {
  const opinions = DEMO_NL2_COUNTER_OPINIONS.filter((o) => o.rev === rev.id)
  return (
    <div className="rounded-[9px] border border-border-light bg-background">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <Pill tone={SEV_TONE[rev.severity]}>{SEV_TEXT[rev.severity]}</Pill>
        <span className="text-[12px] font-medium">{rev.title}</span>
        {rev.verified ? <Pill tone="green">已挂法条</Pill> : <Pill tone="yellow">需律师判断</Pill>}
        {opinions.length > 0 ? <Pill tone="blue">对方 {opinions.length} 条意见</Pill> : null}
        <span className="ml-auto truncate text-[10.5px] text-muted-foreground">{rev.citation}</span>
        <ChevronDown className={cn('size-3 flex-none text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open ? (
        <div className="border-t border-border-light px-3 py-2">
          <div className="rounded-[6px] bg-status-red-bg/60 px-2 py-1.5 text-[10.5px] leading-[1.65] text-status-red line-through decoration-status-red/50">
            {rev.original}
          </div>
          <div className="mt-1 rounded-[6px] bg-status-green-bg/60 px-2 py-1.5 text-[10.5px] leading-[1.65] text-status-green">
            {rev.suggested}
          </div>
          <div className="mt-1.5 text-[10px] text-muted-foreground">立场依据：{rev.stance}</div>
          {opinions.map((o) => (
            <div key={o.id} className="mt-1.5 rounded-[6px] border border-border-light bg-secondary/25 px-2 py-1.5">
              <div className="flex items-center gap-1.5">
                <MessageSquareQuote className="size-3 flex-none text-status-blue" />
                <span className="text-[10.5px] font-medium">{o.author}</span>
                <Pill tone={ATTITUDE_TONE[o.attitude]}>{o.attitude}</Pill>
                <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">{o.at}</span>
              </div>
              <div className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">{o.opinion}</div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
