import { Check, Loader2, Undo2 } from 'lucide-react'

import { REMINDER_TYPE_OPTIONS } from '../constants'
import { formatDueLocal, type CandidateRow } from '../domain'
import { cn } from '@/lib/utils'

interface Props {
  rows: CandidateRow[]
  /** 文字路径（无 candidateId）没有「忽略」与撤销，只有勾选编辑 */
  interactive: boolean
  busy: boolean
  onToggle: (key: string) => void
  onPatch: (key: string, patch: Partial<CandidateRow>) => void
  onSkip: (row: CandidateRow) => void
  onRevoke: (row: CandidateRow) => void
}

const SOURCE_LABELS: Record<string, string> = {
  llm: 'AI',
  merged: 'AI+规则',
  regex: '规则',
  text: '文字',
}

/** 关键日期候选列表：每行 = 勾选 + 时间 + 类型 + 原文摘录 + 状态。
 *  低置信度行虚线边框 + 默认不勾，提示人工核对。 */
export function DateCandidateList({ rows, interactive, busy, onToggle, onPatch, onSkip, onRevoke }: Props) {
  if (rows.length === 0) {
    return <div className="py-4 text-center text-[12px] text-muted-foreground">未识别到关键日期</div>
  }
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r, i) => {
        const editable = r.status === 'pending' && !busy
        const lowConfidence = r.status === 'pending' && r.confidence != null && r.confidence < 0.5
        return (
          <div
            key={r.key}
            style={{ animationDelay: `${Math.min(i, 8) * 55}ms` }}
            className={cn(
              'animate-in fade-in slide-in-from-bottom-1 duration-300 rounded-[10px] border bg-card px-3 py-2.5 transition-colors',
              r.status === 'confirmed' && 'border-status-green/40 bg-status-green-bg',
              r.status === 'skipped' && 'opacity-55',
              lowConfidence && 'border-dashed border-status-yellow/50',
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              {r.status === 'pending' ? (
                <button
                  type="button"
                  onClick={() => onToggle(r.key)}
                  disabled={busy}
                  title={r.checked ? '取消写入' : '勾选写入'}
                  className={cn(
                    'flex h-[16px] w-[16px] flex-none items-center justify-center rounded-[4px] border-[1.5px] transition-all duration-150 active:scale-90',
                    r.checked
                      ? 'border-foreground bg-foreground text-background'
                      : 'border-input text-transparent hover:border-ring/50',
                  )}
                >
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                </button>
              ) : (
                <span className="flex h-[16px] w-[16px] flex-none" />
              )}

              {editable ? (
                <>
                  <input
                    type="datetime-local"
                    className="h-[30px] rounded-[7px] border border-input bg-card px-2 text-[12.5px] tabular-nums outline-none focus:border-ring/40"
                    value={r.dueLocal}
                    onChange={(e) => onPatch(r.key, { dueLocal: e.target.value })}
                  />
                  <select
                    className="h-[30px] rounded-[7px] border border-input bg-card px-1.5 text-[12.5px] outline-none focus:border-ring/40"
                    value={r.reminderType}
                    onChange={(e) => onPatch(r.key, { reminderType: e.target.value })}
                  >
                    {REMINDER_TYPE_OPTIONS.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </>
              ) : (
                <span className="text-[12.5px] font-semibold tabular-nums">
                  {r.status === 'pending' ? r.dueLocal.replace('T', ' ') : formatDueLocal(r.dueLocal)}
                </span>
              )}

              {r.status !== 'pending' && <span className="text-[11px] text-muted-foreground">{r.label}</span>}

              {r.source in SOURCE_LABELS && (
                <span className="rounded-[5px] border border-border bg-secondary px-[6px] py-[1px] text-[9.5px] font-semibold text-secondary-foreground">
                  {SOURCE_LABELS[r.source]}
                </span>
              )}
              {lowConfidence && (
                <span className="rounded-[5px] border border-status-yellow/50 bg-status-yellow-bg px-[6px] py-[1px] text-[9.5px] font-semibold text-status-yellow">
                  低置信·请核对
                </span>
              )}
              {r.confidence != null && (
                <span className="text-[10.5px] tabular-nums text-muted-foreground">{Math.round(r.confidence * 100)}%</span>
              )}

              <span className="ml-auto flex items-center gap-1.5">
                {r.status === 'confirmed' && r.reminderId && (
                  <>
                    <span className="text-[11px] font-semibold text-status-green">已写入 #{r.reminderId}</span>
                    {interactive && (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-[6px] border border-border px-[7px] py-[3px] text-[11px] text-muted-foreground transition-colors hover:border-ring/40 hover:text-foreground"
                        disabled={busy}
                        onClick={() => onRevoke(r)}
                      >
                        <Undo2 className="h-3 w-3" />
                        撤销
                      </button>
                    )}
                  </>
                )}
                {r.status === 'skipped' && <span className="text-[11px] text-muted-foreground">已忽略</span>}
                {r.status === 'pending' && interactive && (
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                    disabled={busy}
                    onClick={() => onSkip(r)}
                  >
                    忽略
                  </button>
                )}
                {busy && r.status === 'pending' && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
              </span>
            </div>

            {r.contextText && (
              <div className="mt-1.5 line-clamp-2 rounded-[7px] border-l-2 border-border bg-secondary/60 px-2.5 py-1.5 text-[11px] leading-[1.5] text-muted-foreground">
                {r.contextText}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
