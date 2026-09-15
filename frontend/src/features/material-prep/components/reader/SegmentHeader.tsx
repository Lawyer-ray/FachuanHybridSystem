import { useState } from 'react'
import { ChevronDown, PencilLine, Scissors, Split } from 'lucide-react'
import { SEGMENT_TYPES } from '../../constants'
import type { DraftState, Segment } from '../../types'
import { segMats } from '../../draft'
import { cn } from '@/lib/utils'

export function SegmentHeader({
  seg,
  si,
  draft,
  color,
  onSetType,
  onRename,
  onMerge,
  onToggleDone,
}: {
  seg: Segment
  si: number
  draft: DraftState
  color: string
  onSetType: (t: string) => void
  onRename: (name: string) => void
  onMerge: () => void
  onToggleDone: () => void
}) {
  const [pickingType, setPickingType] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(seg.fn)

  const srcLabels = segMats(seg)
    .map((mi) => {
      const m = draft.mats[mi]
      return m ? `${m.customName || m.n}` : `材料${mi + 1}`
    })
    .join(' · ')

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
      className="flex items-center gap-2 rounded-[9px] border border-border bg-secondary/60 px-3 py-2"
      style={{ width: '100%' }}
    >
      <span className="h-5 w-1 flex-none rounded-full" style={{ background: color }} />

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
        <span
          onClick={startNameEdit}
          title="点一下改名"
          className="flex min-w-0 flex-1 items-center gap-1 truncate text-[13.5px] font-medium"
        >
          <span className="truncate">{seg.fn}</span>
          <PencilLine className="h-3.5 w-3.5 flex-none text-muted-foreground/70" />
        </span>
      )}

      {/* 来源 */}
      <span className="hidden flex-none text-[11.5px] text-muted-foreground xl:inline">{srcLabels}</span>

      <button
        type="button"
        onClick={onMerge}
        disabled={si === 0}
        title="把这段并入上一份"
        className={cn(
          'flex h-7 flex-none items-center gap-1 rounded-md border border-border bg-card px-2 text-[12px] transition-colors hover:bg-secondary',
          si === 0 ? 'cursor-not-allowed opacity-35' : '',
        )}
      >
        <Split className="h-3.5 w-3.5" />
        并入上一份
      </button>
      <button
        type="button"
        onClick={onToggleDone}
        title="标记为已拆分为独立文件"
        className={cn(
          'flex h-7 flex-none items-center gap-1 rounded-md border px-2 text-[12px] transition-colors',
          seg.done
            ? 'border-green-200 bg-green-50 text-green-700'
            : 'border-border bg-card hover:bg-secondary',
        )}
      >
        <Scissors className="h-3.5 w-3.5" />
        {seg.done ? '已拆分' : '拆分为文件'}
      </button>
    </div>
  )
}
