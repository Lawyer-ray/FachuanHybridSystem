import { useState } from 'react'
import { FileText, Image, Layers, PencilLine } from 'lucide-react'
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
import { SEGMENT_TYPES, SEG_COLORS } from '../../constants'
import type { BundleMat, DraftState, Segment } from '../../types'
import { isAutoSegName, isWholeMat, segMats, segRangeText } from '../../draft'
import { cn } from '@/lib/utils'

/** 名字中部省略：区分信息（-P20.pdf）在尾部，尾部截断等于把区分信息截掉 */
function midEllipsis(s: string, max = 16): string {
  if (s.length <= max) return s
  const tail = Math.floor((max - 1) / 2)
  const head = max - 1 - tail
  return `${s.slice(0, head)}…${s.slice(-tail)}`
}

/** 左栏「源文件 → 段」目录。
 *
 *  每一行：点一下跳到该段；双击 / 右键「重命名」行内改名；右键还能选类型、并入上一份——
 *  拆完材料不用再回正文段头一个个改名。源文件行右键可改源文件名。 */
export function Rail({
  draft,
  onFocusSeg,
  onRenameMat,
  onRenameSeg,
  onSetSegType,
  onMergeSeg,
}: {
  draft: DraftState
  onFocusSeg: (si: number) => void
  onRenameMat: (mi: number) => void
  onRenameSeg: (si: number, name: string) => void
  onSetSegType: (si: number, t: string) => void
  onMergeSeg: (si: number) => void
}) {
  const { mats } = draft

  // 每个素材下挂它的段；跨源段归到「跨源合并」一组
  const groups: { mi: number; segs: number[] }[] = []
  const cross: number[] = []
  draft.segs.forEach((sg, si) => {
    const mis = segMats(sg)
    if (mis.length > 1 || mis.length === 0) {
      cross.push(si)
    } else {
      const g = groups.find((x) => x.mi === mis[0]!)
      if (g) g.segs.push(si)
      else groups.push({ mi: mis[0]!, segs: [si] })
    }
  })

  const matIcon = (m: BundleMat) =>
    m.k === 'pdf' ? (
      <FileText className="h-4 w-4" />
    ) : m.k === 'photo' ? (
      <Image className="h-4 w-4" />
    ) : (
      <Layers className="h-4 w-4" />
    )

  const rowProps = (si: number) => ({
    seg: draft.segs[si]!,
    si,
    whole: isWholeMat(draft, si),
    /** 改过名的整份段显示名字而不是「整份」——名字是用户特意起的 */
    auto: isAutoSegName(draft, draft.segs[si]!),
    /** 未归类 = 没类型且名字还是默认名；改过名的算已处理，行上就安静了 */
    classified: !!draft.segs[si]!.t || !isAutoSegName(draft, draft.segs[si]!),
    color: SEG_COLORS[si % SEG_COLORS.length] ?? SEG_COLORS[0],
    onFocus: () => onFocusSeg(si),
    onRename: (name: string) => onRenameSeg(si, name),
    onSetType: (t: string) => onSetSegType(si, t),
    onMerge: si > 0 ? () => onMergeSeg(si) : undefined,
  })

  return (
    <aside className="flex h-full w-[232px] flex-none flex-col gap-3 overflow-y-auto border-r border-border bg-card p-3 xl:w-[268px]">
      {/* 只留标题：源文件数 / 未归类数顶栏已经说过（未归类在那里是琥珀小标） */}
      <h4 className="px-1 text-sm font-medium">
        材料 <span className="text-xs font-normal text-muted-foreground">{draft.segs.length} 份</span>
      </h4>

      {draft.segs.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">还没有材料。先点右上角新建材料包。</p>
      )}

      {groups.map(({ mi, segs }) => {
        const m = mats[mi]
        if (!m) return null
        const label = m.customName || m.n
        return (
          <div key={mi}>
            <ContextMenu>
              <ContextMenuTrigger asChild>
                <div className="group flex items-center gap-1.5 rounded-md px-1.5 py-1 hover:bg-secondary" title={label}>
                  <span className="text-secondary-foreground">{matIcon(m)}</span>
                  <span className="min-w-0 flex-1 truncate text-[13px]">{midEllipsis(label)}</span>
                  <button
                    type="button"
                    title="改源文件名字"
                    aria-label="改源文件名字"
                    onClick={() => onRenameMat(mi)}
                    // 触屏没有 hover，靠 hover 显形的铅笔永远点不到——无 hover 能力的设备常显
                    className="grid h-5 w-5 flex-none place-items-center rounded text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-card hover:text-foreground [@media(hover:none)]:opacity-100"
                  >
                    <PencilLine className="h-3.5 w-3.5" />
                  </button>
                  <span className="flex-none text-[11px] tabular-nums text-muted-foreground">{m.pages} 页 ↗ {segs.length} 份</span>
                </div>
              </ContextMenuTrigger>
              <ContextMenuContent>
                <ContextMenuItem onSelect={() => onRenameMat(mi)}>重命名源文件</ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
            <div className="ml-2 mt-0.5 flex flex-col gap-0.5 border-l border-zinc-200 pl-2.5">
              {segs.map((si) => (
                <SegRow key={draft.segs[si]!.id} {...rowProps(si)} />
              ))}
            </div>
          </div>
        )
      })}

      {cross.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 px-1.5 py-1 text-[13px] text-secondary-foreground">
            <Layers className="h-4 w-4" />
            <span className="min-w-0 flex-1 truncate">跨源合并</span>
            <span className="text-[11px] tabular-nums text-muted-foreground">{cross.length} 份</span>
          </div>
          <div className="ml-2 mt-0.5 flex flex-col gap-0.5 border-l border-zinc-200 pl-2.5">
            {cross.map((si) => (
              <SegRow key={draft.segs[si]!.id} {...rowProps(si)} crossGroup />
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}

/* ------------------------------------------------------------------ 段行 */

function SegRow({
  seg,
  si,
  whole,
  auto,
  classified,
  color,
  crossGroup = false,
  onFocus,
  onRename,
  onSetType,
  onMerge,
}: {
  seg: Segment
  si: number
  whole: boolean
  auto: boolean
  classified: boolean
  color: string
  crossGroup?: boolean
  onFocus: () => void
  onRename: (name: string) => void
  onSetType: (t: string) => void
  onMerge?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [nameDraft, setNameDraft] = useState(seg.fn)

  const startEdit = () => {
    setNameDraft(seg.fn)
    setEditing(true)
  }
  const commit = () => {
    setEditing(false)
    const name = nameDraft.trim()
    if (name && name !== seg.fn) onRename(name)
  }

  const displayName = whole && auto ? '整份' : seg.fn
  const meta = crossGroup ? `${seg.refs.length} 页` : whole ? '' : segRangeText(seg)
  // pill 只在还有话要说时出现：选了类型显示类型；没处理过提醒未归类；改名已处理的安静
  const pill = seg.t ? (
    <span className="flex-none rounded-full border border-green-200 bg-green-50 px-1.5 text-[10.5px] text-green-700">{seg.t}</span>
  ) : !classified ? (
    <span className="flex-none rounded-full border border-amber-200 bg-amber-50 px-1.5 text-[10.5px] text-amber-700">未归类</span>
  ) : null

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        {/* 外层不能是 button：行内改名的 input 是嵌套交互元素 */}
        <div
          role="button"
          tabIndex={0}
          data-rail-seg={si}
          title={`${seg.fn}\n点击跳转 · 双击改名 · 右键更多`}
          className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => {
            if (!editing) onFocus()
          }}
          onDoubleClick={(e) => {
            e.preventDefault()
            startEdit()
          }}
          onKeyDown={(e) => {
            if (editing) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onFocus()
            } else if (e.key === 'F2') {
              e.preventDefault()
              startEdit()
            }
          }}
        >
          <span
            className={cn(
              'h-2 w-2 flex-none rounded-full',
              crossGroup || seg.t || classified ? 'bg-zinc-400' : 'border border-dashed border-zinc-400',
            )}
            style={!crossGroup && seg.t ? { background: color } : undefined}
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
                if (e.key === 'Escape') setEditing(false)
              }}
              className="h-6 min-w-0 flex-1 rounded border border-zinc-400 bg-white px-1.5 text-[12.5px] outline-none"
            />
          ) : (
            <span className={cn('min-w-0 flex-1 truncate text-[13px]', !classified && 'text-amber-700')}>{midEllipsis(displayName)}</span>
          )}
          {meta && !editing && <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{meta}</span>}
          {!editing && pill}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="min-w-[180px]">
        <ContextMenuItem onSelect={startEdit}>重命名</ContextMenuItem>
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
