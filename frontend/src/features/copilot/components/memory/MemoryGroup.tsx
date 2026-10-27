/**
 * 记忆「分组列表」：一个作用域一段（个人 / 团队 / 律所），只有个人层可删。
 *
 * 从 MemoryDrawer 拆出（后者超软红线）。删除入口只出现在个人层——团队/律所层
 * 由策展提升管理（`MemoryPromoteDialog`），界面给删除钮会与后端口径冲突。
 */

import { Trash2 } from 'lucide-react'

import type { AgentMemoryItem, MemoryScope } from '../../memory-api'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { KIND_LABEL, SCOPE_LABEL } from './labels'

export function MemoryGroup({
  scope,
  items,
  loading,
  onForget,
  forgetting,
}: {
  scope: MemoryScope
  items: AgentMemoryItem[]
  loading: boolean
  onForget: (id: string) => void
  forgetting: boolean
}) {
  return (
    <section className="mb-4" aria-label={SCOPE_LABEL[scope]}>
      <h3 className="mb-1.5 text-[12px] font-[650] text-foreground">
        {SCOPE_LABEL[scope]}
        <span className="ml-1.5 font-normal text-muted-foreground">{items.length}</span>
      </h3>
      {loading && items.length === 0 ? (
        <LoadingBlock size="sm" className="justify-start py-2" />
      ) : items.length === 0 ? (
        <EmptyBlock className="items-start py-2 text-left leading-relaxed">
          还没有记忆。在上方输入，或直接对助手说「记住…」。
        </EmptyBlock>
      ) : (
        <ul className="space-y-1">
          {items.map((memory) => (
            <li
              key={memory.id}
              className="group flex items-start gap-2 rounded-[8px] px-2 py-1.5 transition-colors hover:bg-secondary/60"
            >
              <span className="mt-0.5 flex-none rounded-[5px] bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {KIND_LABEL[memory.kind]}
              </span>
              <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-foreground">{memory.content}</p>
              {memory.hit_count > 0 && (
                <span
                  className="mt-0.5 flex-none text-[10px] text-muted-foreground/70"
                  title={`已注入上下文 ${memory.hit_count} 次`}
                >
                  {memory.hit_count}
                </span>
              )}
              {scope === 'lawyer' && (
                <button
                  type="button"
                  aria-label="删除这条记忆"
                  disabled={forgetting}
                  className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-[5px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive focus:opacity-100"
                  onClick={() => onForget(memory.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
