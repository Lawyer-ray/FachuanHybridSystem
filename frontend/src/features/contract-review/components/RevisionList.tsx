import { Check, MapPin, X } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { bucketRevisions, countBySeverity, severityLabel } from '../domain'
import type { ReviewRevision } from '../types'

/**
 * 左栏：AI 建议清单。
 *
 * 律师的真实动作是「看 AI 想改什么 → 跳到文档对应处 → 采纳或驳回」，
 * 所以每条都带原文（红删线）与改法（绿底），而非只给一句结论。
 * 采纳后沉底到「已处理」，顶部计数实时更新。
 */
export function RevisionList({
  items,
  busyId,
  onDecide,
  onLocate,
}: {
  items: ReviewRevision[]
  busyId: string | null
  onDecide: (rev: ReviewRevision, action: 'accept' | 'reject', reason?: string) => void
  onLocate: (rev: ReviewRevision) => void
}) {
  const { pending, decided } = bucketRevisions(items)
  const counts = countBySeverity(items)
  /** 正在填驳回理由的修订 id */
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  function submitReject(rev: ReviewRevision) {
    onDecide(rev, 'reject', reason.trim())
    setRejectingId(null)
    setReason('')
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-none items-center gap-2 border-b border-border-light px-3.5 py-2.5">
        <span className="text-[12.5px] font-semibold">AI 建议修改</span>
        <span className="rounded-[6px] bg-secondary px-[7px] text-[11px] font-semibold text-secondary-foreground">
          {pending.length}
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          {(counts.high ?? 0) > 0 && <span className="text-status-red">{counts.high} 高</span>}
          {(counts.medium ?? 0) > 0 && <span className="text-status-yellow">{counts.medium} 中</span>}
          {(counts.low ?? 0) > 0 && <span className="text-status-blue">{counts.low} 低</span>}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <SectionLabel text={`待决策 · ${pending.length}`} />
        {pending.length === 0 ? (
          <p className="px-3.5 py-3 text-[11.5px] leading-relaxed text-muted-foreground">
            全部建议已处理完 —— 可以在右侧继续用对话调整，或直接定稿。
          </p>
        ) : (
          pending.map((rev) => (
            <Row
              key={rev.id}
              rev={rev}
              busy={busyId === rev.id}
              rejecting={rejectingId === rev.id}
              reason={reason}
              onReasonChange={setReason}
              onLocate={() => onLocate(rev)}
              onAccept={() => onDecide(rev, 'accept')}
              onStartReject={() => {
                setRejectingId(rev.id)
                setReason('')
              }}
              onCancelReject={() => {
                setRejectingId(null)
                setReason('')
              }}
              onSubmitReject={() => submitReject(rev)}
            />
          ))
        )}

        {decided.length > 0 && (
          <>
            <SectionLabel text={`已处理 · ${decided.length}`} />
            {decided.map((rev) => (
              <Row key={rev.id} rev={rev} busy={false} done />
            ))}
          </>
        )}
      </div>
    </div>
  )
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div className="sticky top-0 z-[1] bg-card px-3.5 py-1.5 text-[10.5px] font-[650] tracking-[0.05em] text-muted-foreground/70">
      {text}
    </div>
  )
}

function Row({
  rev,
  busy,
  done,
  rejecting,
  reason,
  onReasonChange,
  onLocate,
  onAccept,
  onStartReject,
  onCancelReject,
  onSubmitReject,
}: {
  rev: ReviewRevision
  busy: boolean
  done?: boolean
  rejecting?: boolean
  reason?: string
  onReasonChange?: (v: string) => void
  onLocate?: () => void
  onAccept?: () => void
  onStartReject?: () => void
  onCancelReject?: () => void
  onSubmitReject?: () => void
}) {
  const sev = severityLabel(rev.severity)
  return (
    <div
      className={cn(
        'border-b border-border-light px-3.5 py-2.5 transition-opacity',
        done && 'opacity-55',
      )}
    >
      <div className="flex items-baseline gap-1.5">
        {sev && (
          <span
            className={cn(
              'flex-none rounded-[4px] px-[5px] text-[9.5px] font-bold leading-[15px]',
              rev.severity === 'high' && 'bg-status-red-bg text-status-red',
              rev.severity === 'medium' && 'bg-status-yellow-bg text-status-yellow',
              rev.severity === 'low' && 'bg-status-blue-bg text-status-blue',
            )}
          >
            {sev}
          </span>
        )}
        <span className={cn('text-[12.5px] font-semibold', done && 'line-through')}>
          {rev.title || rev.original.slice(0, 20)}
        </span>
      </div>

      <div className="mt-1 text-[11.5px] leading-[1.55] text-muted-foreground">
        <span className="bg-status-red-bg text-status-red line-through">{rev.original}</span>
        <span className="mx-1 text-muted-foreground/60">→</span>
        <span className="bg-status-green-bg text-status-green">{rev.suggested}</span>
      </div>

      {rev.reason && (
        <div className="mt-1 text-[10.5px] leading-[1.5] text-muted-foreground/75">
          {rev.reason}
        </div>
      )}

      {done ? (
        <div className="mt-1.5 text-[10.5px] text-muted-foreground">
          {rev.status === 'accepted' ? '已采纳 · 文档中已留痕' : '已驳回 · 未改动'}
          {rev.reject_reason ? `（${rev.reject_reason}）` : ''}
        </div>
      ) : rejecting ? (
        <div className="mt-2 flex items-center gap-1.5">
          <input
            className="h-[27px] min-w-0 flex-1 rounded-[7px] border border-border bg-card px-2 text-[11.5px] outline-none focus:border-foreground"
            placeholder="驳回理由（可留空，用于 AI 下次改进）"
            value={reason ?? ''}
            onChange={(e) => onReasonChange?.(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSubmitReject?.()
              if (e.key === 'Escape') onCancelReject?.()
            }}
            autoFocus
          />
          <button
            type="button"
            className="h-[27px] rounded-[7px] border border-border px-2.5 text-[11.5px] font-medium transition-colors hover:bg-secondary"
            onClick={onSubmitReject}
          >
            确定
          </button>
          <button
            type="button"
            className="h-[27px] rounded-[7px] px-1.5 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
            onClick={onCancelReject}
          >
            取消
          </button>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-1.5">
          <button
            type="button"
            disabled={busy}
            className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border px-2.5 text-[11.5px] font-medium transition-colors hover:bg-secondary disabled:opacity-50"
            onClick={onLocate}
          >
            <MapPin className="size-3" />
            定位
          </button>
          <button
            type="button"
            disabled={busy}
            className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-foreground bg-foreground px-2.5 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
            onClick={onAccept}
          >
            <Check className="size-3" />
            采纳
          </button>
          <button
            type="button"
            disabled={busy}
            className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border px-2.5 text-[11.5px] font-medium text-muted-foreground transition-colors hover:bg-secondary disabled:opacity-50"
            onClick={onStartReject}
          >
            <X className="size-3" />
            驳回
          </button>
        </div>
      )}
    </div>
  )
}
