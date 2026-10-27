import { useCallback, useMemo, useState, type CSSProperties, type ComponentProps } from 'react'
import { Scissors } from 'lucide-react'
import { SEG_COLORS } from '../../constants'
import { useElementWidth } from '@/hooks/use-element-width'
import type { DraftState, OcrPending, PageKey } from '../../types'
import { selKeyOf } from '../../draft'
import { COL_GAP, effectiveCols, fitPageWidth, rowWidth } from './layout'
import { isAutoSegName } from '../../draft'
import { PageCell, type PageRect } from './PageCell'
import { PageContextMenu } from './PageContextMenu'
import { SegmentHeader } from './SegmentHeader'
import type { FlowOps } from './reader-ops'
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
  onOp: FlowOps
  onToggleSel: (mi: number, p: number, shift: boolean) => void
  onOcrBox: (mi: number, p: number, rect: PageRect) => void
  onRequestDelete: (picked: PageKey[]) => void
}) {
  const { segs, mats, infos } = draft
  const picking = pickInfo >= 0
  // 单源包不展示「源」这个维度：段开始条标不出任何边界，页卡脚注的文件名重复 N 遍也没信息量
  const singleSource = mats.length === 1
  const [flowRef, flowWidth] = useElementWidth<HTMLDivElement>()
  // 右键菜单：记录落点页码；右键非选中页时单删，右键选中页时按当前选区批量删
  const [menu, setMenu] = useState<{ x: number; y: number; mi: number; p: number } | null>(null)

  // —— 列数 / 页宽：原型 sgrid 模型（固定页宽，窄窗保护，缩放联动） ——
  // 列数口径与 Reader 统一走 layout.ts 的 effectiveCols，两处同一套数学
  const nCols = effectiveCols(cols, flowWidth)
  const pageW = fitPageWidth(flowWidth, nCols, zoom)
  const rowW = rowWidth(pageW, nCols)
  const zwide = rowW > flowWidth

  // 每页的来源绿框：一次性预算成 "mi:p" → marks[]，避免每格每渲染重复 O(N×M)，
  // 也让 PageCell 的 marks prop 在 infos 未变时保持引用稳定（memo 才命中得了）
  const marksByPage = useMemo(() => {
    const m = new Map<string, { fi: number; rect: PageRect; label: string }[]>()
    infos.forEach((f, fi) => {
      const sr = f.srcRef
      if (!sr || !sr.rect) return
      const key = selKeyOf({ mi: sr.mi, p: sr.p })
      const list = m.get(key) ?? []
      list.push({ fi, rect: sr.rect, label: f.k })
      m.set(key, list)
    })
    return m
  }, [infos])
  const marksOf = useCallback(
    (mi: number, p: number) => marksByPage.get(selKeyOf({ mi, p })),
    [marksByPage],
  )

  const selKeys = useMemo(() => new Set(selPages.map(selKeyOf)), [selPages])

  const openMenu = useCallback((e: React.MouseEvent, mi: number, p: number) => {
    setMenu({ x: e.clientX, y: e.clientY, mi, p })
  }, [])
  const closeMenu = useCallback(() => setMenu(null), [])

  /** PageCell 的公共 props：两处分支（多列/单列）共用，避免逐字重复的 15 行 props 漂移 */
  const cellPropsOf = useCallback(
    (ref: PageKey): ComponentProps<typeof PageCell> => ({
      messageId,
      mi: ref.mi,
      p: ref.p,
      mat: mats[ref.mi]!,
      hideMatName: singleSource,
      pickActive: picking,
      selModeActive: selMode,
      selected: selKeys.has(`${ref.mi}:${ref.p}`),
      marks: marksOf(ref.mi, ref.p),
      ocrRect: ocrPending && ocrPending.mi === ref.mi && ocrPending.p === ref.p ? ocrPending.rect : null,
      onPickPage: picking ? onOp.pickPage : undefined,
      onOcrBox: picking ? onOcrBox : undefined,
      onToggleSel,
      onContextMenu: openMenu,
    }),
    [messageId, mats, singleSource, picking, selMode, selKeys, marksOf, ocrPending, onOp, onOcrBox, onToggleSel, openMenu],
  )

  const menuInSel = menu ? selKeys.has(`${menu.mi}:${menu.p}`) : false
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
        const color = SEG_COLORS[si % SEG_COLORS.length] ?? SEG_COLORS[0]
        const focused = focusedSeg === si
        const firstMat = seg.refs.length ? mats[seg.refs[0]!.mi] : undefined
        return (
          <section
            key={seg.id}
            id={`seg-${si}`}
            className={`mp-seg flex flex-col gap-1.5 transition-opacity ${focused ? '' : 'opacity-95'}`}
          >
            <SegmentHeader
              seg={seg}
              si={si}
              color={color}
              classified={!!seg.t || !isAutoSegName(draft, seg)}
              onRename={(name) => onOp.renameSeg(si, name)}
              onMerge={() => onOp.mergeSeg(si)}
            />

            {/* 段开始条只在多源包显示：它标的是「这段从哪个源文件开始」，单源时没有边界可标 */}
            {firstMat && !singleSource && (
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
                    // group 挂在页卡包裹层：切分按钮靠 group-hover 显形（漏掉它按钮就永远 opacity-0）
                    <div key={ref.mi + '-' + ref.p} className="group relative flex flex-col gap-1.5">
                      {ri > 0 && (
                        <button
                          type="button"
                          title="在此页前切开"
                          aria-label="在此页前切开"
                          onClick={() => onOp.splitSeg(si, ri - 1)}
                          className="absolute -left-2.5 top-6 z-10 grid h-5 w-5 place-items-center rounded-full border border-dashed border-zinc-300 bg-card text-muted-foreground opacity-0 shadow-sm transition-opacity hover:border-amber-400 hover:text-amber-700 group-hover:opacity-100"
                        >
                          <Scissors className="h-3 w-3" />
                        </button>
                      )}
                      <PageCell {...cellPropsOf(ref)} />
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
                    // group：切开按钮桌面上悬停本页才显形（与多列视图一致），91 个页缝不再常年摆着 91 个按钮
                    <div
                      key={ref.mi + '-' + ref.p}
                      className="group flex w-[var(--mp-cw)] flex-col items-center gap-1.5"
                    >
                      <PageCell {...cellPropsOf(ref)} />
                      {ri < seg.refs.length - 1 && (
                        <button
                          type="button"
                          title="在此切开：把这段从这一页后面分成两份"
                          aria-label="在此切开"
                          onClick={() => onOp.splitSeg(si, ri)}
                          // 桌面：悬停 / 键盘聚焦才显形；触屏没有 hover，常显但压成一根带剪刀的细条
                          className="flex h-[30px] w-full items-center justify-center gap-2 rounded-[6px] border border-dashed border-zinc-300 text-[12px] text-muted-foreground opacity-0 transition-[opacity,border-color,background-color,color] hover:border-amber-400 hover:bg-amber-50 hover:text-amber-700 focus-visible:opacity-100 group-hover:opacity-100 max-[760px]:h-[22px] max-[760px]:opacity-100 [@media(hover:none)]:opacity-100"
                        >
                          <span className="pointer-events-none flex items-center gap-2">
                            <Scissors className="h-3.5 w-3.5" />
                            <span className="max-[760px]:hidden">在此切开</span>
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
          onClose={closeMenu}
        />
      )}
    </div>
  )
}
