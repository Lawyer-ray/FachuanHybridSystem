import { useEffect, useState } from 'react'
import { FileText, Image, Layers, PencilLine } from 'lucide-react'
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from '@/components/ui/context-menu'
import { SEG_COLORS } from '../../constants'
import type { BundleMat, DraftState } from '../../types'
import { isAutoSegName, isWholeMat, segMats } from '../../draft'
import { RailSegRow, type DropPos } from './RailSegRow'

/**
 * 左栏「源文件 → 段」目录。
 *
 * 行交互：点一下跳到该段；⌘/Ctrl+点 多选、⇧+点 选区间（选 ≥2 份时顶部出现操作条，
 * 可并成一份）；双击 / 右键「重命名」行内改名；右键选类型 / 并入上一份；
 * 拖拽行到另一行的上半 / 下半 = 移动段序（学预览 App 的页列表，插入线实时可见）。
 * 源文件行右键可改源文件名。
 */
export function Rail({
  draft,
  onFocusSeg,
  onRenameMat,
  onRenameSeg,
  onSetSegType,
  onMergeSeg,
  onMergeSegs,
  onMoveSeg,
}: {
  draft: DraftState
  onFocusSeg: (si: number) => void
  onRenameMat: (mi: number) => void
  onRenameSeg: (si: number, name: string) => void
  onSetSegType: (si: number, t: string) => void
  onMergeSeg: (si: number) => void
  onMergeSegs: (sis: number[]) => void
  onMoveSeg: (si: number, targetSi: number, position: 'before' | 'after') => void
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

  const [sel, setSel] = useState<number[]>([])
  const [anchor, setAnchor] = useState<number | null>(null)
  const [editingSi, setEditingSi] = useState<number | null>(null)
  const [dragSi, setDragSi] = useState<number | null>(null)
  const [drop, setDrop] = useState<{ si: number; pos: DropPos } | null>(null)

  // 段数量变化（切开 / 合并 / 删页）后选择与改名态都可能指向漂移的下标，一律清掉
  useEffect(() => {
    setSel([])
    setAnchor(null)
    setEditingSi(null)
  }, [draft.segs.length])

  const rowProps = (si: number) => ({
    seg: draft.segs[si]!,
    si,
    whole: isWholeMat(draft, si),
    auto: isAutoSegName(draft, draft.segs[si]!),
    classified: !!draft.segs[si]!.t || !isAutoSegName(draft, draft.segs[si]!),
    color: SEG_COLORS[si % SEG_COLORS.length] ?? SEG_COLORS[0],
    selected: sel.includes(si),
    dropPos: drop?.si === si ? drop.pos : null,
    editing: editingSi === si,
    onStartEdit: () => setEditingSi((v) => (v === si ? null : si)),
    onFocus: () => {
      setSel([])
      setAnchor(si)
      onFocusSeg(si)
    },
    onSelectRow: (e: React.MouseEvent) => {
      if (e.shiftKey && anchor !== null) {
        const range: number[] = []
        for (let i = Math.min(anchor, si); i <= Math.max(anchor, si); i++) range.push(i)
        setSel(range)
        return
      }
      setSel((cur) => (cur.includes(si) ? cur.filter((x) => x !== si) : [...cur, si].sort((a, b) => a - b)))
      setAnchor(si)
    },
    onRename: (name: string) => onRenameSeg(si, name),
    onSetType: (t: string) => onSetSegType(si, t),
    onMerge: si > 0 ? () => onMergeSeg(si) : undefined,
    onDragStartRow: () => setDragSi(si),
    onHoverDrop: (pos: DropPos) => {
      if (dragSi !== si) setDrop({ si, pos })
    },
    // dragSi / drop 读的是最新渲染的闭包（rowProps 每次 render 重建），dragOver 期间
    // setDrop 触发的重渲会让 drop 时拿到最新值
    onDropRow: () => {
      if (dragSi !== null && drop && drop.si !== dragSi) onMoveSeg(dragSi, drop.si, drop.pos)
      setDragSi(null)
      setDrop(null)
    },
    onDragEndRow: () => {
      setDragSi(null)
      setDrop(null)
    },
  })

  const mergeSelected = () => {
    if (sel.length >= 2) onMergeSegs([...sel].sort((a, b) => a - b))
    setSel([])
  }

  const matIcon = (m: BundleMat) =>
    m.k === 'pdf' ? (
      <FileText className="h-4 w-4" />
    ) : m.k === 'photo' ? (
      <Image className="h-4 w-4" />
    ) : (
      <Layers className="h-4 w-4" />
    )

  return (
    <aside className="flex h-full w-[232px] flex-none flex-col gap-3 overflow-y-auto border-r border-border bg-card p-3 xl:w-[268px]">
      <h4 className="px-1 text-sm font-medium">
        材料 <span className="text-xs font-normal text-muted-foreground">{draft.segs.length} 份</span>
      </h4>

      {draft.segs.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">还没有材料。先点右上角新建材料包。</p>
      )}

      {/* 多选操作条：⌘/⇧+点 行选中 ≥2 份时出现 */}
      {sel.length >= 2 && (
        <div className="sticky top-0 z-10 flex items-center gap-1.5 rounded-lg border border-border bg-card/95 px-2 py-1.5 text-[12px] shadow-sm backdrop-blur">
          <span className="flex-none text-muted-foreground">已选 {sel.length} 份</span>
          <button
            type="button"
            onClick={mergeSelected}
            className="ml-auto rounded-md bg-foreground px-2 py-1 text-[12px] font-medium text-background hover:bg-zinc-700"
          >
            合并为一份
          </button>
          <button type="button" onClick={() => setSel([])} className="text-muted-foreground hover:text-foreground">
            取消
          </button>
        </div>
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
                  <span className="min-w-0 flex-1 truncate text-[13px]">{label}</span>
                  <button
                    type="button"
                    title="改源文件名字"
                    aria-label="改源文件名字"
                    onClick={() => onRenameMat(mi)}
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
                <RailSegRow key={draft.segs[si]!.id} {...rowProps(si)} />
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
              <RailSegRow key={draft.segs[si]!.id} {...rowProps(si)} crossGroup />
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
