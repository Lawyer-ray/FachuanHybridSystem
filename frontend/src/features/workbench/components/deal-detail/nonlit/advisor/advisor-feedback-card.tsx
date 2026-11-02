/**
 * 常年顾问 · 客户满意度回访
 *
 * 常法合同续不续，很大程度上看客户怎么评价这一年。回访记录按月一条，
 * 分数用 5 个点的星条（不借助图标库：点阵更紧凑，一眼比得出高低）。
 */

import { useState } from 'react'

import { cn } from '@/lib/utils'

import { DEMO_NL3_SATISFACTION } from '../../demo-nonlit'
import { Card } from '../../ui'

const CHANNEL_TONE: Record<string, string> = {
  电话: 'border-border bg-secondary text-secondary-foreground',
  微信: 'border-status-green/40 bg-status-green-bg text-status-green',
  现场: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
}

export function AdvisorFeedbackCard() {
  const [open, setOpen] = useState<string | null>(DEMO_NL3_SATISFACTION[0]?.id ?? null)
  const avg = Math.round((DEMO_NL3_SATISFACTION.reduce((s, r) => s + r.score, 0) / DEMO_NL3_SATISFACTION.length) * 10) / 10

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">客户满意度回访</h3>
        <span className="text-[11px] text-muted-foreground">
          {DEMO_NL3_SATISFACTION.length} 次 · 平均 {avg} 分（5 分制）
        </span>
        <span className="ml-auto text-[10.5px] text-muted-foreground">点开看客户原话</span>
      </div>

      <div className="mt-2.5 flex flex-col divide-y divide-border-light overflow-hidden rounded-[9px] border border-border-light bg-background">
        {DEMO_NL3_SATISFACTION.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setOpen(open === r.id ? null : r.id)}
            className="w-full px-3 py-2 text-left transition-colors hover:bg-secondary/40"
          >
            <div className="flex items-center gap-2">
              <span className="w-[38px] flex-none text-[10.5px] tabular-nums text-muted-foreground">
                {r.date.slice(5)}
              </span>
              <ScoreDots score={r.score} />
              <span
                className={cn(
                  'flex-none rounded-[5px] border px-1.5 text-[10px] font-semibold',
                  CHANNEL_TONE[r.channel],
                )}
              >
                {r.channel}
              </span>
              <span className="min-w-0 flex-1 truncate text-[11.5px] text-secondary-foreground">{r.interviewer}</span>
              <span
                className={cn(
                  'flex-none text-[11px] font-[620] tabular-nums',
                  r.score >= 4 ? 'text-status-green' : r.score >= 3 ? 'text-status-yellow' : 'text-status-red',
                )}
              >
                {r.score}.0
              </span>
            </div>
            {open === r.id ? (
              <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">「{r.feedback}」</p>
            ) : null}
          </button>
        ))}
      </div>
    </Card>
  )
}

/** 5 点星条：实心=已得分 */
function ScoreDots({ score }: { score: number }) {
  return (
    <span className="flex flex-none items-center gap-[2px]" title={`${score} / 5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={cn(
            'size-[6px] rounded-full',
            i < score ? (score >= 4 ? 'bg-status-green' : 'bg-status-yellow') : 'bg-border',
          )}
        />
      ))}
    </span>
  )
}
