import { useState } from 'react'
import { Check, Loader2, Pencil, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { DirectEditCandidate } from '../types'

/**
 * 划词直改的候选卡片组。
 *
 * **与 RevisionList 的区别**：那是审查流水线的「风险建议清单」（带等级、依据、
 * 采纳/驳回的完整决策流，一条条过 30 处）；这里是「同一段话的几种说法」，
 * 律师挑一条就完事，只需一个采纳动作，不存在驳回——没选中的候选自动作废。
 *
 * 所以不复用 RevisionList：那套组件的视觉语言（等级徽标、驳回理由、沉底到
 * 「已处理」）在这里全是噪音。
 */
export function DirectEditCandidates({
  selection,
  candidates,
  onAccept,
  busyIndex,
}: {
  selection: string
  candidates: DirectEditCandidate[]
  /** 采纳第 i 条；父级负责调接口与刷新编辑器 */
  onAccept: (index: number, candidate: DirectEditCandidate) => void
  /** 正在落盘的那条（其余按钮禁用，防重复提交） */
  busyIndex: number | null
}) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (!candidates.length) return null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
        <Sparkles className="size-3" />
        <span>
          为「{selection.length > 24 ? `${selection.slice(0, 24)}…` : selection}」生成 {candidates.length} 个改法
        </span>
      </div>

      {candidates.map((c, i) => {
        const busy = busyIndex === i
        const disabled = busyIndex !== null
        const isOpen = expanded === i
        // 长改写默认折叠到 6 行，律师可以点开看全文——
        // 直接全展开会让三条候选把面板撑得很高，反而看不清差异。
        const long = c.suggested.length > 180
        return (
          <div
            key={i}
            className={cn(
              'rounded-[10px] border border-border bg-card p-3 transition-colors',
              !disabled && 'hover:border-foreground/25',
            )}
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-muted-foreground">改法 {i + 1}</span>
              {c.reason && <span className="truncate text-[11px] text-muted-foreground">{c.reason}</span>}
            </div>

            <p
              className={cn(
                'whitespace-pre-wrap text-[12.5px] leading-relaxed text-foreground',
                long && !isOpen && 'line-clamp-6',
              )}
            >
              {c.suggested}
            </p>

            {long && (
              <button
                type="button"
                className="mt-1 text-[11px] text-muted-foreground underline-offset-2 hover:underline"
                onClick={() => setExpanded(isOpen ? null : i)}
              >
                {isOpen ? '收起' : '展开全文'}
              </button>
            )}

            <div className="mt-2 flex items-center gap-1.5">
              <button
                type="button"
                disabled={disabled}
                className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-foreground bg-foreground px-2.5 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
                onClick={() => onAccept(i, c)}
              >
                {busy ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />}
                {busy ? '写入中…' : '采纳这条'}
              </button>
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Pencil className="size-3" />
                以修订痕迹写入
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
