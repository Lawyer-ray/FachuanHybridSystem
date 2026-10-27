import { useState } from 'react'
import { PencilLine, Split } from 'lucide-react'
import { segRangeText } from '../../draft'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

export function SegmentHeader({
  seg,
  si,
  color,
  classified,
  onRename,
  onMerge,
}: {
  seg: Segment
  si: number
  color: string
  /** 已归类 = 选了类型或改过名。未归类时名字亮琥珀——这是「这份还没处理」的唯一提醒 */
  classified: boolean
  onRename: (name: string) => void
  onMerge: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [nameDraft, setNameDraft] = useState(seg.fn)

  // 页区间 + 页数：「P5–19 · 15 页」；跨源「跨源 · 15 页」。切几刀后名字再像，看区间就分得开
  const rangeText = `${segRangeText(seg)} · ${seg.refs.length} 页`

  const startNameEdit = () => {
    setNameDraft(seg.fn)
    setEditing(true)
  }
  const commitName = () => {
    setEditing(false)
    if (nameDraft.trim() && nameDraft.trim() !== seg.fn) onRename(nameDraft.trim())
  }

  return (
    <div
      className="relative flex items-center gap-2 rounded-[9px] border border-transparent bg-transparent py-2 pl-4 pr-3 transition-colors hover:border-zinc-200 hover:bg-[#fafafa] max-[760px]:gap-1.5 max-[760px]:pl-3 max-[760px]:pr-1.5"
      style={{ width: '100%' }}
    >
      <span className="absolute left-0 top-2 bottom-2 w-[4px] flex-none rounded-full" style={{ background: color }} />

      {/* 名字是唯一控件：改个名就算归类（名字恰是类型词还会自动分类）。
          以前这里还有一个独立的类型胶囊，跟名字说同一件事，已撤——类型收进右键菜单 */}
      {editing ? (
        <input
          autoFocus
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitName()
            if (e.key === 'Escape') setEditing(false)
          }}
          className="h-7 min-w-0 flex-1 rounded-md border border-zinc-400 bg-white px-2 text-[13px] outline-none"
        />
      ) : (
        <button
          type="button"
          onClick={startNameEdit}
          title={classified ? '点一下改名' : '还没归类：点一下给这份起个名（名字是类型词会自动分类），或右键选类型'}
          className={cn(
            'flex min-w-0 flex-1 items-center gap-1 truncate text-left text-[13.5px] font-medium',
            !classified && 'text-amber-700',
          )}
        >
          <span className="truncate">{seg.fn}</span>
          <PencilLine className="h-3.5 w-3.5 flex-none text-muted-foreground/70" />
        </button>
      )}

      {seg.reviewFlag === 'low_confidence' || seg.reviewFlag === 'unrecognized' ? (
        <span
          className="flex-none rounded-full bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-800"
          title={`自动识别置信度 ${Math.round((seg.confidence ?? 0) * 100)}%，请核对页段边界和材料名称`}
        >
          建议复核
        </span>
      ) : null}

      {/* 页区间（原型 rg） */}
      <span className="hidden flex-none text-[11.5px] tabular-nums text-muted-foreground @min-[1024px]:inline">{rangeText}</span>

      {/* 并入上一份：首段没有上一份，不渲染（灰按钮是给「永远点不了」的动作留座 */}
      {si > 0 && (
        <button
          type="button"
          onClick={onMerge}
          title="把这段并入上一份"
          aria-label="并入上一份"
          className="flex h-7 flex-none items-center gap-1 rounded-md border border-border bg-card px-2 text-[12px] transition-colors hover:bg-secondary max-[760px]:w-7 max-[760px]:justify-center max-[760px]:px-0"
        >
          <Split className="h-3.5 w-3.5" />
          <span className="max-[760px]:hidden">并入上一份</span>
        </button>
      )}
    </div>
  )
}
