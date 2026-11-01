/**
 * 逐条采纳修订：从第 1 条开始，一条一条停下问「采纳还是驳回」
 *
 * 为什么不一次性「全部采纳」：跨境合同的修订都要落到对方的还价上，
 * 律师真正的工作是**一条一条拍板**，而且中途会被电话打断、下次接着走。
 * 这里的进度落在本地状态里，走进任何一条都能看到「已采纳 N / 驳回 M / 还剩 K」。
 */

import { useState } from 'react'
import { Check, ChevronRight, RotateCcw, Scale, X } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_TH_CONTRACT_REVISIONS, type DemoContractRevision } from '../../demo-nonlit'
import { ActionButton, Card } from '../../ui'
import { TonePill as Pill } from './crossborder-ui'
import { nextRevision, walkStats } from './crossborder-domain'

const REVS = DEMO_TH_CONTRACT_REVISIONS

export function RevisionWalkCard({
  decided,
  onDecide,
  onReset,
  onPickRev,
}: {
  decided: Record<string, 'accept' | 'reject'>
  onDecide: (id: string, verdict: 'accept' | 'reject') => void
  onReset: () => void
  onPickRev: (id: string) => void
}) {
  const [started, setStarted] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const stats = walkStats(REVS, decided)
  const current: DemoRevisionOrNull = nextRevision(REVS, decided)
  const walked = stats.accepted + stats.rejected

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[13px] font-[620]">逐条采纳修订</h3>
        <span className="text-[11px] text-muted-foreground">
          第 {Math.min(walked + (stats.done ? 0 : 1), REVS.length)} / {REVS.length} 条
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {started ? (
            <button
              type="button"
              onClick={() => setPickerOpen((v) => !v)}
              className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[11.5px] text-secondary-foreground hover:bg-secondary"
            >
              <Scale className="size-3" /> 跳到某条
            </button>
          ) : null}
          <ActionButton sm onClick={onReset}>
            <RotateCcw className="size-3" /> 重新走
          </ActionButton>
        </div>
      </div>

      {/* 进度条：已走完的比例 */}
      <div className="mt-2.5 h-[5px] overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full rounded-full transition-[width] duration-300', stats.done ? 'bg-status-green' : 'bg-foreground')}
          style={{ width: `${Math.round((walked / REVS.length) * 100)}%` }}
        />
      </div>

      {!started ? (
        <div className="mt-2.5 flex items-center gap-3 rounded-[9px] border border-border-light bg-background px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium">5 条修订等你逐条拍板</div>
            <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              从第 1 条开始走，每条停下来问「采纳还是驳回」。第 5 条无外国法依据，需要你自己判断。
            </div>
          </div>
          <ActionButton dark onClick={() => setStarted(true)}>
            <ChevronRight className="size-3.5" /> 开始逐条走
          </ActionButton>
        </div>
      ) : null}

      {pickerOpen ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {REVS.map((r, i) => (
            <button
              key={r.id}
              type="button"
              onClick={() => {
                onPickRev(r.id)
                setPickerOpen(false)
              }}
              className="inline-flex h-[24px] items-center gap-1 rounded-[6px] border border-border-light bg-background px-2 text-[10.5px] hover:bg-secondary"
            >
              <span className="tabular-nums text-muted-foreground">{i + 1}</span>
              {r.title}
              {decided[r.id] ? <Check className="size-2.5 text-status-green" /> : null}
            </button>
          ))}
        </div>
      ) : null}

      {started && current ? (
        <div className="mt-2.5 rounded-[9px] border border-status-yellow/50 bg-status-yellow-bg/30 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Pill tone="yellow">待拍板</Pill>
            <span className="text-[12px] font-medium">{current.title}</span>
            <span className="text-[10.5px] text-muted-foreground">{current.citation}</span>
            <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">
              第 {walked + 1} / {REVS.length} 条
            </span>
          </div>
          <div className="mt-1.5 rounded-[6px] bg-status-red-bg/50 px-2 py-1 text-[10.5px] leading-[1.6] text-status-red line-through decoration-status-red/50">
            {current.original}
          </div>
          <div className="mt-1 rounded-[6px] bg-status-green-bg/60 px-2 py-1 text-[10.5px] leading-[1.6] text-status-green">
            {current.suggested}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-muted-foreground">
              {current.verified ? `已挂法条 · ${current.stance}` : '无外国法依据 · 需律师判断'}
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <ActionButton dark onClick={() => onDecide(current.id, 'accept')}>
                <Check className="size-3.5" /> 采纳这条
              </ActionButton>
              <ActionButton onClick={() => onDecide(current.id, 'reject')}>
                <X className="size-3.5" /> 驳回
              </ActionButton>
            </div>
          </div>
        </div>
      ) : null}

      {started && stats.done ? (
        <div className="mt-2.5 rounded-[9px] border border-status-green/40 bg-status-green-bg/40 px-3 py-2">
          <div className="text-[12px] font-medium text-status-green">
            已走完：采纳 {stats.accepted} 条 / 驳回 {stats.rejected} 条
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {REVS.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => onPickRev(r.id)}
                className={cn(
                  'inline-flex items-center gap-1 rounded-[6px] border px-2 text-[10.5px] leading-[1.7]',
                  decided[r.id] === 'accept'
                    ? 'border-status-green/40 bg-status-green-bg text-status-green'
                    : 'border-status-red/40 bg-status-red-bg text-status-red',
                )}
              >
                {decided[r.id] === 'accept' ? <Check className="size-2.5" /> : <X className="size-2.5" />}
                {r.title}
              </button>
            ))}
          </div>
          <div className="mt-1.5 text-[10px] text-muted-foreground">
            采纳的 {stats.accepted} 条会写进修订稿；驳回的 {stats.rejected} 条留在谈判清单里，对方还价可再拉回来。
          </div>
        </div>
      ) : null}

      {/* 已决定但没走完时的摘要 */}
      {started && !stats.done && walked > 0 ? (
        <div className="mt-2 flex items-center gap-2 text-[10.5px] text-muted-foreground">
          <span className="text-status-green">已采纳 {stats.accepted}</span>
          <span>·</span>
          <span className="text-status-red">已驳回 {stats.rejected}</span>
          <span>·</span>
          <span>还剩 {REVS.length - walked} 条</span>
        </div>
      ) : null}
    </Card>
  )
}

type DemoRevisionOrNull = DemoContractRevision | null
