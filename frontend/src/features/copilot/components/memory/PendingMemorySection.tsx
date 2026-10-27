/**
 * 待确认区：AI 自动抽取 / 行为推断产出的记忆，确认后才进上下文。
 *
 * 从 MemoryDrawer 拆出（后者超软红线）。**必须置顶**：它是「自动抽取进上下文」
 * 的唯一闸门，折叠进普通列表等于闸门形同虚设。
 */

import { Check, Sparkles, X } from 'lucide-react'

import type { AgentMemoryItem } from '../../memory-api'
import { Button } from '@/components/ui/button'
import { KIND_LABEL } from './labels'

export function PendingMemorySection({
  pending,
  pendingBusy,
  onConfirm,
}: {
  pending: AgentMemoryItem[]
  /** 确认/忽略请求在途：两个「全部」按钮一起禁用，避免连点打两遍 */
  pendingBusy: boolean
  /** accept=false 是「忽略」——不要写成通过 */
  onConfirm: (ids: string[], accept: boolean) => void
}) {
  if (pending.length === 0) return null
  return (
    <section className="mb-5" aria-label="待确认的记忆">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-[12px] font-[650] text-foreground">
          <Sparkles className="h-3.5 w-3.5 opacity-70" />
          待确认 {pending.length} 条
        </h3>
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-[11px]"
            disabled={pendingBusy}
            onClick={() => onConfirm(pending.map((m) => m.id), false)}
          >
            全部忽略
          </Button>
          <Button
            size="sm"
            className="h-7 px-2 text-[11px]"
            disabled={pendingBusy}
            onClick={() => onConfirm(pending.map((m) => m.id), true)}
          >
            全部确认
          </Button>
        </div>
      </div>
      <ul className="space-y-1.5">
        {pending.map((memory) => (
          <li key={memory.id} className="rounded-[10px] border border-dashed border-border bg-secondary/40 px-3 py-2.5">
            <p className="text-[13px] leading-relaxed text-foreground">{memory.content}</p>
            <div className="mt-2 flex items-center gap-2">
              <span className="rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {KIND_LABEL[memory.kind]}
              </span>
              <span className="text-[10px] text-muted-foreground">
                置信度 {(memory.confidence * 100).toFixed(0)}%
              </span>
              <div className="ml-auto flex gap-1">
                <button
                  type="button"
                  aria-label="忽略这条记忆"
                  className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  onClick={() => onConfirm([memory.id], false)}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  aria-label="确认这条记忆"
                  className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-foreground hover:text-background"
                  onClick={() => onConfirm([memory.id], true)}
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
