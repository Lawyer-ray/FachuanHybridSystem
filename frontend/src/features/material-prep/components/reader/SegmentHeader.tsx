import { useState } from 'react'
import { ChevronDown, PencilLine, Split } from 'lucide-react'
import { SEGMENT_TYPES } from '../../constants'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

export function SegmentHeader({
  seg,
  si,
  color,
  onSetType,
  onRename,
  onMerge,
}: {
  seg: Segment
  si: number
  color: string
  onSetType: (t: string) => void
  onRename: (name: string) => void
  onMerge: () => void
}) {
  const [pickingType, setPickingType] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(seg.fn)

  const last = seg.refs[seg.refs.length - 1]
  // 页数只说一次；跨源补充来源数——起止页码 P{x}–{y} 与页数重复（页卡自己有编号），不再展示
  const cross = seg.refs.length > 0 && seg.refs[0]!.mi !== last?.mi
  const rangeText = cross ? `${seg.refs.length} 页 · 跨源` : `${seg.refs.length} 页`

  const startNameEdit = () => {
    setNameDraft(seg.fn)
    setEditingName(true)
  }
  const commitName = () => {
    setEditingName(false)
    if (nameDraft.trim() && nameDraft.trim() !== seg.fn) onRename(nameDraft.trim())
  }

  return (
    <div
      className="relative flex items-center gap-2 rounded-[9px] border border-transparent bg-transparent py-2 pl-4 pr-3 transition-colors hover:border-zinc-200 hover:bg-[#fafafa] max-[760px]:gap-1.5 max-[760px]:pl-3 max-[760px]:pr-1.5"
      style={{ width: '100%' }}
    >
      <span className="absolute left-0 top-2 bottom-2 w-[4px] flex-none rounded-full" style={{ background: color }} />

      {/* 类型胶囊 */}
      {pickingType ? (
        <select
          autoFocus
          value={seg.t}
          onChange={(e) => {
            onSetType(e.target.value)
            setPickingType(false)
          }}
          onBlur={() => setPickingType(false)}
          className="h-7 flex-none rounded-md border border-zinc-400 bg-white px-2 text-[13px] outline-none"
        >
          <option value="">— 选择类型 —</option>
          {SEGMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      ) : (
        <button
          type="button"
          onClick={() => setPickingType(true)}
          title="点一下选材料类型"
          className={cn(
            'flex h-7 flex-none items-center gap-1 rounded-full border px-2.5 text-[12px] font-medium transition-colors',
            seg.t
              ? 'border-green-200 bg-green-50 text-green-700'
              : 'border-amber-200 bg-amber-50 text-amber-700',
          )}
        >
          {seg.t || '未归类'}
          <ChevronDown className="h-3 w-3 opacity-60" />
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

      {/* 段名 */}
      {editingName ? (
        <input
          autoFocus
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitName()
            if (e.key === 'Escape') setEditingName(false)
          }}
          className="h-7 min-w-0 flex-1 rounded-md border border-zinc-400 bg-white px-2 text-[13px] outline-none"
        />
      ) : (
        <button
          type="button"
          onClick={startNameEdit}
          title="点一下改名"
          className="flex min-w-0 flex-1 items-center gap-1 truncate text-left text-[13.5px] font-medium"
        >
          <span className="truncate">{seg.fn}</span>
          <PencilLine className="h-3.5 w-3.5 flex-none text-muted-foreground/70" />
        </button>
      )}

      {/* 页数（原型 rg） */}
      <span className="hidden flex-none text-[11.5px] tabular-nums text-muted-foreground lg:inline">{rangeText}</span>

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
