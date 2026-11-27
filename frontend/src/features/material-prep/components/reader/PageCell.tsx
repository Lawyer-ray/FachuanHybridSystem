import { memo, useRef, useState } from 'react'
import type { BundleMat, RectPrecision, RotDeg } from '../../types'
import { rotateNormRect } from '../../draft/page-rotation'
import { rectPrecisionOf } from '../../types'
import { cn } from '@/lib/utils'

import { EngineBoxOverlay, type EngineBoxGroup } from './EngineBoxOverlay'
import { PageBody } from './PageBody'
import { resolveDragRect, type PageRect } from './ui'

/**
 * 普通定位框的描边样式（按精度分四档）。
 *
 * 以前只有「虚线/实线」两种，而 ``approx`` 同时盖了两种完全不同的不可信程度——
 * 整页大框（坐标无意义）与表格半格框（左右列对齐、纵向行高不均）画出来一模一样，
 * 律师无法判断值不值得去核对。分档后：
 *   exact → 实线（引擎原生 bbox，可信）
 *   grid  → 实线 + 稍深一档、线宽 1.5px（原表**实测**格子，可信且比 exact 更「实」：
 *           复核表格时要能一眼看出「这个框是量表量出来的，不是按列数除出来的」）
 *   cell  → 虚线（均分**推算**，列宽悬殊时会整列偏出去，必须去核）
 *   page  → 虚线 + 更淡（坐标基本无意义，仅提示「这里有内容」）
 *
 * ⚠️ 未知取值一律落到最后一档（最淡）：后端加了新档位而这里没跟上时，宁可画得不确定，
 * 也不能让律师以为它是量出来的。`grid` 必须在 `exact` 之前判——两者都是实线，
 * 落到 `exact` 分支就等于把新档位吃掉（视觉上无从区分，白改后端）。
 */
function hitBoxClass(h: { approx?: boolean; precision?: RectPrecision }): string {
  const precision = h.precision ?? rectPrecisionOf(h)
  if (precision === 'grid') return 'border-[1.5px] border-sky-700/80'
  if (precision === 'exact') return 'border border-sky-500/70'
  if (precision === 'cell') return 'border border-sky-500/60 border-dashed'
  return 'border border-sky-500/40 border-dashed'
}


export const PageCell = memo(function PageCell({
  messageId,
  mi,
  p,
  mat,
  hideMatName = false,
  pickActive,
  selModeActive,
  selected,
  marks = [],
  hits = [],
  engineBoxes = null,
  focusedHitKey = null,
  ocrRect,
  onPickPage,
  onOcrBox,
  onToggleSel,
  onContextMenu,
  onActivateHit,
  rotation = 0,
}: {
  messageId: number
  mi: number
  p: number
  mat: BundleMat
  /** 单源包：脚注不再每页重复同一个文件名，只留页码 */
  hideMatName?: boolean
  pickActive?: boolean
  selModeActive?: boolean
  selected?: boolean
  marks?: { fi: number; rect: PageRect; label: string }[]
  /** 识别定位框：云端识别出的正文块位置（与 marks 的来源绿框分开配色，
   *  免得律师分不清"字段出处"和"块位置"） */
  hits?: { key: string; rect: PageRect; label: string; approx?: boolean; precision?: RectPrecision }[]
  /** 双框对照：高亮一条引擎分歧时，同时画两个引擎的框（null = 没有分歧被高亮）。
   *  用 SVG 而不是 div 画：虚线描边、半透明填充与「框旁小字」都要精确控制，
   *  DOM 边框做得到的（border-style: dashed）在不同浏览器上划线长度不一，两份引擎就难分。 */
  engineBoxes?: EngineBoxGroup[] | null
  /** 当前被 Markdown 面板选中的块 key：该框加亮，其余淡化（原文对照的视觉锚点） */
  focusedHitKey?: string | null
  /** 双击某个定位框：把这块回传给 Markdown 面板（高亮 + 进入修改） */
  onActivateHit?: (key: string) => void
  /** 页旋转角度（顺时针增量）。页转了，叠在页上的识别框也必须跟着转 */
  rotation?: RotDeg
  ocrRect?: PageRect | null
  onPickPage?: (mi: number, p: number) => void
  onOcrBox?: (mi: number, p: number, rect: PageRect) => void
  onToggleSel?: (mi: number, p: number, shift: boolean) => void
  onContextMenu?: (e: React.MouseEvent, mi: number, p: number) => void
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const movedRef = useRef(false)
  // 拖框矩形走 ref 供 pointerup 判定（state 只管渲染蓝色框）：
  // pointermove 与 pointerup 可能同帧批处理，读 state 闭包会拿到旧值，
  // 把一次有效拖框误判成「只点了一下记页码」——这正是规范「高频路径用 ref」的场景
  const rectRef = useRef<PageRect | null>(null)
  const [dragRect, setDragRect] = useState<PageRect | null>(null)

  const stopProp = (e: React.SyntheticEvent) => e.stopPropagation()

  const onPointerDown = (e: React.PointerEvent) => {
    if (!pickActive || e.button !== 0) return
    const r = boxRef.current?.getBoundingClientRect()
    if (!r) return
    dragRef.current = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }
    movedRef.current = false
    rectRef.current = null
    setDragRect(null)
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      /* noop */
    }
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current || !pickActive) return
    const r = boxRef.current?.getBoundingClientRect()
    if (!r) return
    const cur = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }
    // 只有构成有效拖框（位移超过阈值）才记录矩形并显示蓝框；阈值内的手抖
    // 位移一律归 null——否则 pointerup 时 rect 非 null 又不满足拖框条件，
    // 两个分支都不进，1px~阈值之间就成了点击死区
    const rect = resolveDragRect(dragRef.current, cur)
    if (rect) movedRef.current = true
    rectRef.current = rect
    setDragRect(rect)
  }

  const onPointerUp = () => {
    if (!dragRef.current || !pickActive) return
    dragRef.current = null
    const rect = rectRef.current
    rectRef.current = null
    setDragRect(null)
    // resolveDragRect 保证 rectRef 非空 ⇔ 位移超过阈值（有效拖框）
    if (rect) {
      onOcrBox?.(mi, p, rect)
    } else {
      onPickPage?.(mi, p)
    }
  }

  const onClick = (e: React.MouseEvent) => {
    if (pickActive || movedRef.current) return
    const mod = e.metaKey || e.ctrlKey
    if (selModeActive || mod || e.shiftKey) {
      e.preventDefault()
      onToggleSel?.(mi, p, e.shiftKey)
    }
  }

  return (
    <div
      data-mi={mi}
      data-p={p}
      // 选页模式下整页可点选（toggle），补键盘可达；取字（画框）/默认阅读态是
      // pointer 专属交互，不进 tab 序（否则每页 PDF 都成一个 tab 停靠点）
      role={selModeActive ? 'button' : undefined}
      tabIndex={selModeActive ? 0 : undefined}
      aria-pressed={selModeActive ? selected : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onClick={onClick}
      onKeyDown={
        selModeActive
          ? (ev) => {
              if (ev.key !== 'Enter' && ev.key !== ' ') return
              ev.preventDefault()
              onToggleSel?.(mi, p, false)
            }
          : undefined
      }
      onDragStart={stopProp}
      onContextMenu={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onContextMenu?.(e, mi, p)
      }}
      className={cn(
        // w-full：撑满外层列宽（--mp-cw）。页卡自身不定宽时，骨架屏阶段会在
        // items-center 容器里被内容宽收缩成一条窄卡（手机上整页只剩中间一小条）
        'relative w-full select-text rounded-[7px] border bg-card text-[12.5px] leading-[1.9] text-foreground shadow-[0_1px_3px_rgba(0,0,0,0.05),0_10px_26px_rgba(0,0,0,0.04)] transition-opacity',
        pickActive ? 'cursor-crosshair select-none' : selModeActive ? 'cursor-pointer' : 'cursor-default',
        selected && 'border-zinc-800 ring-2 ring-zinc-800/80',
        selModeActive && !selected && 'opacity-35',
        pickActive && !selected && 'border-amber-300/70 ring-1 ring-amber-300/50',
      )}
    >
      {/* 图像区：页体 + 全部定位框共用同一个盒子做百分比基准。
          ⚠️ 定位框**不能**直接挂在外层页卡上：rect 是相对**页面图像**的归一化值，
          而外层页卡还含底部页码栏（约 27px）。两者分母不同会让框越靠下偏得越多
          （实测页高 800px 时底部偏 +24px、框高也被等比放大）。 */}
      <div ref={boxRef} className="relative w-full">
        <PageBody messageId={messageId} p={p} mat={mat} rotation={rotation} />

        {/* 来源标注：采纳后的绿框 */}
        {marks.map((m) => {
          const rect = rotateNormRect(m.rect, rotation)
          return (
          <div
            key={m.fi}
            className="pointer-events-auto absolute rounded-[3px] border-[1.5px] border-green-500/80"
            style={{
              left: `${rect.x * 100}%`,
              top: `${rect.y * 100}%`,
              width: `${rect.w * 100}%`,
              height: `${rect.h * 100}%`,
            }}
          >
            <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-green-600 px-1 text-[10px] leading-4 text-white">
              {m.label}
            </span>
          </div>
          )
        })}

        {/* 识别定位：云端识别出的正文块（实线=量出来的 / 虚线=推算 / 最淡虚线=整页近似） */}
        {hits.map((h) => {
          const on = focusedHitKey === h.key
          const hitRect = rotateNormRect(h.rect, rotation)
          // 有选中块时其余框淡化：不同时亮一片，才看得出「这一条对应哪一个框」
          const dim = focusedHitKey != null && !on
          return (
          <div
            key={h.key}
            role={onActivateHit ? 'button' : undefined}
            onDoubleClick={
              onActivateHit
                ? (e) => {
                    // 阻止冒泡：否则会触发页面的「记来源/拖框」等单击行为
                    e.stopPropagation()
                    onActivateHit(h.key)
                  }
                : undefined
            }
            className={`absolute rounded-[3px] border ${
              onActivateHit ? 'pointer-events-auto cursor-pointer' : 'pointer-events-none'
            } ${
              on
                ? 'border-2 border-sky-600 bg-sky-400/20 shadow-[0_0_0_2px_rgba(2,132,199,0.25)]'
                : `${hitBoxClass(h)}`
            } ${dim ? 'opacity-25' : ''}`}
            style={{
              left: `${hitRect.x * 100}%`,
              top: `${hitRect.y * 100}%`,
              width: `${hitRect.w * 100}%`,
              height: `${hitRect.h * 100}%`,
            }}
            title={h.label}
          />
          )
        })}

        {/* 双引擎对照框：实线绿 = MinerU（主），虚线琥珀 = VL（副）。
            画在 hits 之后、拖框之前：分歧框是律师当前要看的东西，不能被普通定位框
            盖住；而拖框/待确认框是律师刚画的操作反馈，必须还在最上面。 */}
        {engineBoxes && <EngineBoxOverlay groups={engineBoxes} rotation={rotation} />}

        {/* OCR 拖出的框 */}
        {dragRect && (
          <div
            className="pointer-events-none absolute rounded-[3px] border-2 border-blue-500/90 bg-blue-500/10"
            style={{
              left: `${dragRect.x * 100}%`,
              top: `${dragRect.y * 100}%`,
              width: `${dragRect.w * 100}%`,
              height: `${dragRect.h * 100}%`,
            }}
          />
        )}

        {/* 待确认的 OCR 框 */}
        {ocrRect && (
          <div
            className="pointer-events-none absolute rounded-[3px] border-2 border-green-500 bg-blue-500/10"
            style={{
              left: `${ocrRect.x * 100}%`,
              top: `${ocrRect.y * 100}%`,
              width: `${ocrRect.w * 100}%`,
              height: `${ocrRect.h * 100}%`,
            }}
          >
            <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-zinc-800 px-1 text-[10px] leading-4 text-white opacity-0" />
          </div>
        )}
      </div>

      {/* 选页已选：右上角黑圆勾（原型 .rp.picked::after） */}
      {selected && (
        <span className="pointer-events-none absolute right-3 top-3 grid h-[22px] w-[22px] place-items-center rounded-full bg-zinc-900 text-[13px] font-bold leading-none text-white">
          ✓
        </span>
      )}

      <div className="flex items-center justify-between gap-2 rounded-b-[7px] border-t border-border/60 bg-card px-3 py-1.5 text-[11px] text-muted-foreground">
        {!hideMatName && <span className="truncate">{mat.customName || mat.n}</span>}
        {rotation !== 0 && (
          <span
            className="flex-none rounded-[4px] border border-status-blue/30 bg-status-blue-bg px-1 py-px text-[10px] font-medium text-status-blue"
            title="这一页已旋转；归案 / 归档 / 下载时会按这个方向输出"
          >
            {rotation}°
          </span>
        )}
        <span className="ml-auto tabular-nums">
          {p} / {mat.pages}
        </span>
      </div>
    </div>
  )
})
