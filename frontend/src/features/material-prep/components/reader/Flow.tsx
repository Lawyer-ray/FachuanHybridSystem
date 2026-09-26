import { useState, type CSSProperties } from 'react'
import { Scissors } from 'lucide-react'
import { SEG_COLORS } from '../../constants'
import { useElementWidth } from '../../hooks/use-element-width'
import type { DraftState, OcrPending, PageKey } from '../../types'
import { selKeyOf } from '../../draft'
import { COL_GAP, fitPageWidth, maxColsAllowed, rowWidth } from './layout'
import { PageCell, type PageRect } from './PageCell'
import { PageContextMenu } from './PageContextMenu'
import { SegmentHeader } from './SegmentHeader'
import { cn } from '@/lib/utils'

export function Flow({
  draft,
  messageId,
  pickInfo,
  focusedSeg,
  zoom,
  cols,
  selMode,
  selPages,
  ocrPending,
  onOp,
  onToggleSel,
  onOcrBox,
  onRequestDelete,
}: {
  draft: DraftState
  messageId: number
  pickInfo: number
  focusedSeg: number
  zoom: number
  cols: number
  selMode: boolean
  selPages: PageKey[]
  ocrPending: OcrPending | null
  onOp: {
    setSegType: (si: number, t: string) => void
    renameSeg: (si: number, name: string) => void
    mergeSeg: (si: number) => void
    toggleDone: (si: number) => void
    splitSeg: (si: number, k: number) => void
    pickPage: (mi: number, p: number) => void
  }
  onToggleSel: (mi: number, p: number, shift: boolean) => void
  onOcrBox: (mi: number, p: number, rect: PageRect) => void
  onRequestDelete: (picked: PageKey[]) => void
}) {
  const { segs, mats, infos } = draft
  const picking = pickInfo >= 0
  const [flowRef, flowWidth] = useElementWidth<HTMLDivElement>()
  // 右键菜单：记录落点页码；右键非选中页时单删，右键选中页时按当前选区批量删
  const [menu, setMenu] = useState<{ x: number; y: number; mi: number; p: number } | null>(null)

  // —— 列数 / 页宽：原型 sgrid 模型（固定页宽，窄窗保护，缩放联动） ——
  const maxCols = maxColsAllowed(flowWidth)
  const nCols = Math.max(1, Math.min(cols, maxCols))
  const pageW = fitPageWidth(flowWidth, nCols, zoom)
  const rowW = rowWidth(pageW, nCols)
  const zwide = rowW > flowWidth

  // 每页的来源绿框（采纳了带框的标来源）
  const marksOf = (mi: number, p: number) =>
    infos
      .map((f, fi) => {
        const sr = f.srcRef
        if (!sr || sr.mi !== mi || sr.p !== p || !sr.rect) return null
        return { fi, rect: sr.rect, label: f.k }
      })
      .filter((x): x is { fi: number; rect: PageRect; label: string } => x !== null)

  const openMenu = (e: React.MouseEvent, mi: number, p: number) => {
    setMenu({ x: e.clientX, y: e.clientY, mi, p })
  }
  const menuInSel = menu ? selPages.some((k) => selKeyOf(k) === `${menu.mi}:${menu.p}`) : false
  const menuTitle = menu
    ? `${mats[menu.mi]?.customName || mats[menu.mi]?.n || ''} · 第 ${menu.p} 页`
    : ''

  return (
    <div
      ref={flowRef}
      className={cn('mp-flow flex flex-col gap-5 py-6', zwide && 'mp-flow-zwide')}
      style={
        {
          width: '100%',
          '--mp-cols': nCols,
          '--mp-cw': `${pageW}px`,
          '--mp-gap': `${COL_GAP}px`,
          '--mp-rw': `${rowW}px`,
        } as CSSProperties
      }
    >
      {segs.map((seg, si) => {
        const color = SEG_COLORS[si % SEG_COLORS.length]
        const focused = focusedSeg === si
        const firstMat = mats[seg.refs[0]?.mi]
        return (
          <section
            key={si}
            id={`seg-${si}`}
            className={`mp-seg flex flex-col gap-1.5 transition-opacity ${focused ? '' : 'opacity-95'}`}
          >
            <SegmentHeader
              seg={seg}
              si={si}
              color={color}
              onSetType={(t) => onOp.setSegType(si, t)}
              onRename={(name) => onOp.renameSeg(si, name)}
              onMerge={() => onOp.mergeSeg(si)}
              onToggleDone={() => onOp.toggleDone(si)}
            />

            {firstMat && (
              <div className="w-full rounded-[7px] border border-dashed border-zinc-300 py-1 text-center text-[11px] text-muted-foreground">
                段开始 · {firstMat.customName || firstMat.n}
              </div>
            )}

            {nCols > 1 ? (
              <div className="mp-grid">
                {seg.refs.map((ref, ri) => {
                  const mat = mats[ref.mi]
                  if (!mat) return null
                  return (
                    <div key={ref.mi + '-' + ref.p} className="relative flex flex-col gap-1.5">
                      {ri > 0 && (
                        <button
                          type="button"
                          title="在此页前切开"
                          onClick={() => onOp.splitSeg(si, ri - 1)}
                          className="absolute -left-2.5 top-6 z-10 grid h-5 w-5 place-items-center rounded-full border border-dashed border-zinc-300 bg-card text-muted-foreground opacity-0 shadow-sm transition-opacity hover:border-amber-400 hover:text-amber-700 group-hover:opacity-100"
                        >
                          <Scissors className="h-3 w-3" />
                        </button>
                      )}
                      <PageCell
                        messageId={messageId}
                        mi={ref.mi}
                        p={ref.p}
                        mat={mat}
                        pickActive={picking}
                        selModeActive={selMode}
                        selected={selPages.some((k) => selKeyOf(k) === `${ref.mi}:${ref.p}`)}
                        marks={marksOf(ref.mi, ref.p)}
                        ocrRect={ocrPending && ocrPending.mi === ref.mi && ocrPending.p === ref.p ? ocrPending.rect : null}
                        onPickPage={picking ? onOp.pickPage : undefined}
                        onOcrBox={picking ? onOcrBox : undefined}
                        onToggleSel={onToggleSel}
                        onContextMenu={openMenu}
                      />
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className={cn('flex flex-col items-center gap-1.5', zwide && 'items-start')}>
                {seg.refs.map((ref, ri) => {
                  const mat = mats[ref.mi]
                  if (!mat) return null
                  return (
                    <div
                      key={ref.mi + '-' + ref.p}
                      className="flex w-[var(--mp-cw)] flex-col items-center gap-1.5"
                    >
                      <PageCell
                        messageId={messageId}
                        mi={ref.mi}
                        p={ref.p}
                        mat={mat}
                        pickActive={picking}
                        selModeActive={selMode}
                        selected={selPages.some((k) => selKeyOf(k) === `${ref.mi}:${ref.p}`)}
                        marks={marksOf(ref.mi, ref.p)}
                        ocrRect={ocrPending && ocrPending.mi === ref.mi && ocrPending.p === ref.p ? ocrPending.rect : null}
                        onPickPage={picking ? onOp.pickPage : undefined}
                        onOcrBox={picking ? onOcrBox : undefined}
                        onToggleSel={onToggleSel}
                        onContextMenu={openMenu}
                      />
                      {ri < seg.refs.length - 1 && (
                        <button
                          type="button"
                          title="在此切开：把这段从这一页后面分成两份"
                          onClick={() => onOp.splitSeg(si, ri)}
                          className="group flex h-[30px] w-full items-center justify-center gap-2 rounded-[6px] border border-dashed border-zinc-300 text-[12px] text-muted-foreground transition-all hover:border-amber-400 hover:bg-amber-50 hover:text-amber-700"
                        >
                          <span className="pointer-events-none flex items-center gap-2">
                            <Scissors className="h-3.5 w-3.5" />
                            在此切开
                          </span>
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}

      {menu && (
        <PageContextMenu
          x={menu.x}
          y={menu.y}
          title={menuTitle}
          count={menuInSel ? selPages.length : 1}
          onDelete={() => {
            const target = menuInSel ? selPages : [{ mi: menu.mi, p: menu.p }]
            onRequestDelete(target)
            setMenu(null)
          }}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  )
}
