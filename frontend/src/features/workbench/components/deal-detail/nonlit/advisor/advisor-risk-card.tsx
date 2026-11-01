/**
 * 常年顾问 · 风险提示清单
 *
 * 常法服务的价值一半在「出了事给意见」，另一半在「提前告诉客户哪里要出事」。
 * 这里把律师该主动提醒的事项列成清单：合同到期、用工风险、合规缺口三类，
 * 每条带到期日与建议动作；按类别筛、按等级排序，未闭环的排前面。
 */

import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_NL3_RISKS, type DemoNl3Risk } from '../../demo-nonlit'
import { Card } from '../../ui'

type RiskFilter = '全部' | DemoNl3Risk['category']

const FILTERS: RiskFilter[] = ['全部', '合同到期', '用工风险', '合规缺口']

const LEVEL_TONE: Record<DemoNl3Risk['level'], string> = {
  高: 'border-status-red/40 bg-status-red-bg text-status-red',
  中: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
  低: 'border-border bg-secondary text-secondary-foreground',
}

export function AdvisorRiskCard() {
  const [filter, setFilter] = useState<RiskFilter>('全部')
  const [open, setOpen] = useState<string | null>(null)
  const [closed, setClosed] = useState<string[]>(DEMO_NL3_RISKS.filter((r) => r.closed).map((r) => r.id))

  const rows = DEMO_NL3_RISKS.filter((r) => filter === '全部' || r.category === filter)
    .slice()
    .sort((a, b) => Number(closed.includes(a.id)) - Number(closed.includes(b.id)))

  const high = DEMO_NL3_RISKS.filter((r) => r.level === '高' && !closed.includes(r.id)).length
  const openCount = DEMO_NL3_RISKS.filter((r) => !closed.includes(r.id)).length

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">风险提示清单</h3>
        <span className="text-[11px] text-muted-foreground">
          未闭环 {openCount} 项 · 高等级 {high} 项
        </span>
        <span className="ml-auto text-[10.5px] text-muted-foreground">合同到期 / 用工 / 合规缺口</span>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => {
          const n = f === '全部' ? DEMO_NL3_RISKS.length : DEMO_NL3_RISKS.filter((r) => r.category === f).length
          const on = f === filter
          return (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={cn(
                'inline-flex h-[24px] items-center gap-1 rounded-[7px] border px-2 text-[11px] font-[550] transition-colors',
                on
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
              )}
            >
              {f} {n}
            </button>
          )
        })}
      </div>

      <div className="mt-2 flex flex-col divide-y divide-border-light overflow-hidden rounded-[9px] border border-border-light bg-background">
        {rows.map((r) => {
          const isClosed = closed.includes(r.id)
          return (
            <div key={r.id}>
              <button
                type="button"
                onClick={() => setOpen(open === r.id ? null : r.id)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
              >
                <span
                  className={cn(
                    'flex-none rounded-[5px] border px-1.5 text-[10px] font-semibold',
                    LEVEL_TONE[r.level],
                  )}
                >
                  {r.level}
                </span>
                <span className="w-[54px] flex-none truncate text-[10px] text-muted-foreground">{r.category}</span>
                <span
                  className={cn(
                    'min-w-0 flex-1 truncate text-[11.5px]',
                    isClosed ? 'text-muted-foreground line-through' : 'text-foreground',
                  )}
                  title={r.title}
                >
                  {r.title}
                </span>
                <span className="flex-none text-[10px] tabular-nums text-muted-foreground">{r.due}</span>
                {isClosed ? (
                  <span className="flex-none rounded-[5px] border border-status-green/40 bg-status-green-bg px-1.5 text-[10px] font-semibold text-status-green">
                    已闭环
                  </span>
                ) : (
                  <AlertTriangle className="size-3 flex-none text-status-yellow" />
                )}
              </button>
              {open === r.id ? (
                <div className="flex flex-col gap-1.5 border-t border-border-light bg-secondary/20 px-3 pt-1.5 pb-2.5">
                  <div className="text-[10.5px] leading-[1.6]">
                    <span className="text-muted-foreground">影响：</span>
                    {r.impact}
                  </div>
                  <div className="text-[10.5px] leading-[1.6]">
                    <span className="text-muted-foreground">建议动作：</span>
                    {r.action}
                  </div>
                  {isClosed ? null : (
                    <button
                      type="button"
                      onClick={() => setClosed((v) => [...v, r.id])}
                      className="self-start rounded-[6px] border border-border bg-card px-2 py-[2px] text-[10.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
                    >
                      标记已闭环
                    </button>
                  )}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
