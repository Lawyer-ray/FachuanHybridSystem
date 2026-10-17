import { useState } from 'react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { SEGMENT_TYPES } from '../../constants'
import { segRangeText } from '../../draft'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

/** 名字中部省略：区分信息（-P20.pdf）在尾部，尾部截断等于把区分信息截掉 */
function midEllipsis(s: string, max = 16): string {
  if (s.length <= max) return s
  const tail = Math.floor((max - 1) / 2)
  const head = max - 1 - tail
  return `${s.slice(0, head)}…${s.slice(-tail)}`
}

export type DropPos = 'before' | 'after'

/**
 * 左栏的一行段：点击跳转、⌘/⇧点 多选、双击（或右键→重命名）行内改名、
 * 右键选类型 / 并入上一份、拖拽移动段序（上半=插到前面，下半=插到后面）。
 *
 * 类型没有 pill：选了类型名字会自动变成「类型.pdf」，元数据在右键菜单里改。
 */
export function RailSegRow({
  seg,
  si,
  whole,
  auto,
  classified,
  color,
  crossGroup = false,
  selected = false,
  dropPos = null,
  editing,
  onStartEdit,
  onFocus,
  onSelectRow,
  onRename,
  onSetType,
  onMerge,
  onDragStartRow,
  onHoverDrop,
  onDropRow,
  onDragEndRow,
}: {
  seg: Segment
  si: number
  whole: boolean
  auto: boolean
  classified: boolean
  color: string
  crossGroup?: boolean
  selected?: boolean
  /** 本行正被拖拽悬停的插入位置（上半 / 下半） */
  dropPos?: DropPos | null
  /** 行内改名由父层持有（右键「重命名」也要打开它） */
  editing: boolean
  onStartEdit: () => void
  onFocus: () => void
  /** 带修饰键的点击（多选 / 区间选），e 传下去判断 meta/ctrl/shift */
  onSelectRow: (e: React.MouseEvent) => void
  onRename: (name: string) => void
  onSetType: (t: string) => void
  onMerge?: () => void
  onDragStartRow: () => void
  /** dragOver 悬停时上报插入位置（上半 / 下半） */
  onHoverDrop: (pos: DropPos) => void
  /** 提交拖拽：位置由父层从 dragOver 状态里取 */
  onDropRow: () => void
  onDragEndRow: () => void
}) {
  const [nameDraft, setNameDraft] = useState(seg.fn)

  const commit = () => {
    const name = nameDraft.trim()
    if (name && name !== seg.fn) onRename(name)
  }

  const displayName = whole && auto ? '整份' : seg.fn
  const meta = crossGroup ? `${seg.refs.length} 页` : whole ? '' : segRangeTextLocal(seg)

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          role="button"
          tabIndex={0}
          data-rail-seg={si}
          data-selected={selected || undefined}
          draggable={!editing}
          title={`${seg.fn}\n点击跳转 · ⌘/⇧点 多选 · 双击改名 · 右键更多`}
          className={cn(
            'relative flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring',
            selected && 'bg-secondary/70 ring-1 ring-foreground/25',
            !classified && 'text-amber-700',
          )}
          onClick={(e) => {
            if (editing) return
            if (e.metaKey || e.ctrlKey || e.shiftKey) {
              onSelectRow(e)
              return
            }
            onFocus()
          }}
          onDoubleClick={(e) => {
            e.preventDefault()
            onStartEdit()
          }}
          onKeyDown={(e) => {
            if (editing) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onFocus()
            } else if (e.key === 'F2') {
              e.preventDefault()
              onStartEdit()
            }
          }}
          onDragStart={(e) => {
            e.dataTransfer.setData('text/plain', String(si))
            e.dataTransfer.effectAllowed = 'move'
            onDragStartRow()
          }}
          onDragOver={(e) => {
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
            const r = e.currentTarget.getBoundingClientRect()
            onHoverDrop(e.clientY < r.top + r.height / 2 ? 'before' : 'after')
          }}
          onDrop={(e) => {
            e.preventDefault()
            onDropRow()
          }}
          onDragEnd={onDragEndRow}
        >
          {/* 拖拽插入线：上半=插到本行前，下半=插到本行后 */}
          {dropPos && (
            <span
              className={cn(
                'absolute right-0 left-0 z-10 h-[3px] rounded-full bg-foreground/70',
                dropPos === 'before' ? '-top-[3px]' : '-bottom-[3px]',
              )}
            />
          )}
          <span
            className={cn(
              'h-2 w-2 flex-none rounded-full',
              seg.t ? '' : 'bg-zinc-400',
              !seg.t && !classified && 'border border-dashed border-amber-400 bg-transparent',
            )}
            style={seg.t ? { background: color } : undefined}
          />
          {editing ? (
            <input
              autoFocus
              aria-label="材料名"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={commit}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                e.stopPropagation()
                if (e.key === 'Enter') commit()
                if (e.key === 'Escape') onStartEdit()
              }}
              className="h-6 min-w-0 flex-1 rounded border border-zinc-400 bg-white px-1.5 text-[12.5px] outline-none"
            />
          ) : (
            <span className="min-w-0 flex-1 truncate text-[13px]">{midEllipsis(displayName)}</span>
          )}
          {meta && !editing && <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{meta}</span>}
          {!editing && seg.reviewFlag === 'low_confidence' ? (
            <span className="flex-none text-[10px] text-amber-700" title="自动识别置信度低，建议核对">
              复核
            </span>
          ) : null}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="min-w-[180px]">
        <ContextMenuItem onSelect={onStartEdit}>重命名</ContextMenuItem>
        <ContextMenuSub>
          <ContextMenuSubTrigger>选类型</ContextMenuSubTrigger>
          <ContextMenuSubContent className="max-h-[320px] overflow-y-auto">
            <ContextMenuRadioGroup value={seg.t} onValueChange={onSetType}>
              {SEGMENT_TYPES.map((t) => (
                <ContextMenuRadioItem key={t} value={t}>
                  {t}
                </ContextMenuRadioItem>
              ))}
            </ContextMenuRadioGroup>
            {seg.t && (
              <>
                <ContextMenuSeparator />
                <ContextMenuItem onSelect={() => onSetType('')}>清除类型</ContextMenuItem>
              </>
            )}
          </ContextMenuSubContent>
        </ContextMenuSub>
        {onMerge && (
          <>
            <ContextMenuSeparator />
            <ContextMenuItem onSelect={onMerge}>并入上一份</ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}

/** 页区间文案：连续「P5–19」、断续「P3, P7–9」、跨源「跨源」——labels.segRangeText 的本地别名 */
const segRangeTextLocal = segRangeText
