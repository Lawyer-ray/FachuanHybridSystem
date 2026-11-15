import { memo, useEffect, useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import type { BundleMat, EngineBlockRect, EngineName, EngineVariant, RectPrecision } from '../../types'
import { rectPrecisionOf } from '../../types'
import { engineShortLabel } from '../../draft'
import { cn } from '@/lib/utils'

import { PdfPageView } from './PdfPageView'
import { PhotoPageView } from './PhotoPageView'
import { SkeletonLines } from './SkeletonLines'
import { resolveDragRect, type PageRect } from './ui'

// 兼容出口：PageRect 类型已随拖框判定迁至 ui.ts，历史导入路径（Flow / use-ocr）保持可用
export type { PageRect } from './ui'

/**
 * 双框对照的配色与画法（契约【视觉规则】的硬要求）。
 *
 * - 主引擎 MinerU = **实线** `#16a34a`（绿）
 * - 副引擎 VL = **虚线** `#f59e0b`（琥珀），`5 3` 划线样式
 * - 半透明填充 `fillOpacity 0.12`：两框大面积重叠时仍能两框的边都看见
 *   （不透明填充会把先画的那个完全盖住，正是要避免的情形）
 * - `approx`（整页近似框，坐标不可信）统一用更淡的描边：不给假精度
 */
const ENGINE_BOX_COLORS: Record<string, string> = {
  mineru: '#16a34a',
  paddleocr_vl: '#f59e0b',
  textin: '#6366f1',
}
const ENGINE_BOX_DEFAULT_COLOR = '#71717a'
/** 主引擎：实线。其余走虚线——契约只点名 MinerU 是主引擎 */
const PRIMARY_ENGINE: EngineName = 'mineru'
/** 虚线间隔（契约写死 5 3） */
const ENGINE_BOX_DASH = '5 3'
/** 描边宽度用 px 且不随 viewBox 缩放：页面图宽上千像素，按比例算会细成一条看不见的线 */
const ENGINE_BOX_STROKE = 2

/**
 * 普通定位框的描边样式（按精度分三档）。
 *
 * 以前只有「虚线/实线」两种，而 ``approx`` 同时盖了两种完全不同的不可信程度——
 * 整页大框（坐标无意义）与表格半格框（左右列对齐、纵向行高不均）画出来一模一样，
 * 律师无法判断值不值得去核对。三档分开后：
 *   exact → 实线（可信）
 *   cell  → 虚线（八九不离十，可去核）
 *   page  → 虚线 + 更淡（坐标基本无意义，仅提示「这里有内容」）
 */
function hitBoxClass(h: { approx?: boolean; precision?: RectPrecision }): string {
  const precision = h.precision ?? rectPrecisionOf(h)
  if (precision === 'exact') return 'border border-sky-500/70'
  if (precision === 'cell') return 'border border-sky-500/60 border-dashed'
  return 'border border-sky-500/40 border-dashed'
}
/** viewBox 的归一化边长：所有坐标乘以它就是 px，不用再量化 */
const VIEWBOX = 1000

/** 一个引擎在某页上的框 + 该引擎这一处的文本（框旁标注要说清「这个框说的是什么」） */
export interface EngineBoxGroup {
  variant: EngineVariant
  blocks: EngineBlockRect[]
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
        <PageBody messageId={messageId} p={p} mat={mat} />

        {/* 来源标注：采纳后的绿框 */}
        {marks.map((m) => (
          <div
            key={m.fi}
            className="pointer-events-auto absolute rounded-[3px] border-[1.5px] border-green-500/80"
            style={{
              left: `${m.rect.x * 100}%`,
              top: `${m.rect.y * 100}%`,
              width: `${m.rect.w * 100}%`,
              height: `${m.rect.h * 100}%`,
            }}
          >
            <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-green-600 px-1 text-[10px] leading-4 text-white">
              {m.label}
            </span>
          </div>
        ))}

        {/* 识别定位：云端识别出的正文块（虚线=整页近似框，不给假精度） */}
        {hits.map((h) => {
          const on = focusedHitKey === h.key
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
              left: `${h.rect.x * 100}%`,
              top: `${h.rect.y * 100}%`,
              width: `${h.rect.w * 100}%`,
              height: `${h.rect.h * 100}%`,
            }}
            title={h.label}
          />
          )
        })}

        {/* 双引擎对照框：实线绿 = MinerU（主），虚线琥珀 = VL（副）。
            画在 hits 之后、拖框之前：分歧框是律师当前要看的东西，不能被普通定位框
            盖住；而拖框/待确认框是律师刚画的操作反馈，必须还在最上面。 */}
        {engineBoxes && <EngineBoxOverlay groups={engineBoxes} />}

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
        <span className="ml-auto tabular-nums">
          {p} / {mat.pages}
        </span>
      </div>
    </div>
  )
})

/** 选择页体渲染分支：视口外的页只挂骨架占位，滚近了才真正取附件渲染。
 *  92 页的大包若全部立即 mount，会同时拉取全部附件并渲染全部页位图
 *  （DPR 感知宽度下单页 ~21MB，见 PdfPageView 的驻留 img 说明）。 */
function PageBody({ messageId, p, mat }: { messageId: number; p: number; mat: BundleMat }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (shown) return
    const el = hostRef.current
    // 环境不支持 IntersectionObserver 时直接渲染（退化到旧行为）
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShown(true)
      return
    }
    // 上下各预渲染约两屏：滚动到达时内容已在，骨架只是首开瞬间的占位
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((en) => en.isIntersecting)) setShown(true)
      },
      { rootMargin: '1600px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [shown])

  if (!shown) {
    return (
      <div ref={hostRef} className="w-full bg-white">
        <SkeletonLines />
      </div>
    )
  }
  if (mat.k === 'pdf') return <PdfPageView messageId={messageId} partIndex={mat.partIndex} pageNum={p} />
  if (mat.k === 'photo') return <PhotoPageView messageId={messageId} partIndex={mat.partIndex} />
  return <OfficePlaceholder mat={mat} />
}

function OfficePlaceholder({ mat }: { mat: BundleMat }) {
  return (
    <div className="flex aspect-[3/4] flex-col items-center justify-center gap-3 bg-zinc-50 p-6 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-xl bg-secondary text-secondary-foreground">
        <FileText className="h-7 w-7" />
      </span>
      <div>
        <p className="text-sm font-medium">{mat.n}</p>
        <p className="mt-1 max-w-[220px] text-[11px] leading-relaxed text-muted-foreground">
          Word / Excel 等格式当前按整份处理，暂不能逐页切分
        </p>
      </div>
    </div>
  )
}

/**
 * 双引擎对照框（SVG 覆盖层，与页图同尺寸、绝对定位铺满）。
 *
 * ## 坐标口径
 *
 * 复用既有约定：`rect` 是**相对页面图像**归一化的 0-1（`PositionedBlock.rect` 同口径，
 * 见外层 `boxRef` 容器的注释）。这里把 0-1 乘上 viewBox 边长再交给 SVG，
 * 而不是另建一套像素换算——页卡宽度随缩放/列数变化，用 px 画会在每次缩放后失准。
 * `preserveAspectRatio="none"` 让 viewBox 直接拉满容器，于是 `x*100%` 与 `x*VIEWBOX`
 * 是同一个点，两套口径不会漂移。
 *
 * ## 为什么叠在一个 `<svg>` 里而不是每框一个 div
 *
 * 两框大面积重叠时，两个独立绝对定位元素的填充会互相遮挡，谁在后谁看得见。
 * 统一用 `fillOpacity: 0.12` 的半透明填充 + 描边，重叠处颜色自然叠深，
 * 而两条边都完整可见——这正是「两框重叠时都可见」的实现方式。
 *
 * ## 退化情形
 *
 * 某引擎这一页一个框都没给（后端没传 block bbox / 该引擎降级失败）时，它那一组
 * 渲染不出任何 rect，页面上只有另一个引擎的框。这是刻意的：**不伪造一个假框去凑
 * 成一对**，缺坐标就如实缺着——假框会让律师对着一个不存在的差异下结论。
 * 坐标不可信（`approx`）的框描边更淡并在小字前加「≈」：宁可看着不确定，也不给假精度。
 */
function EngineBoxOverlay({ groups }: { groups: EngineBoxGroup[] }) {
  // 一条分歧通常只对应一个块，所以按整组判断「本引擎坐标是否可信」。
  // 一组里混着精确框与近似框时，只要有一个精确框就按精确处理（有精确信息就别放弃它）。
  const entries = groups.map((g) => {
    const color = ENGINE_BOX_COLORS[g.variant.engine] ?? ENGINE_BOX_DEFAULT_COLOR
    const dashed = g.variant.engine !== PRIMARY_ENGINE
    // 坐标可信度按「最差的那个块」算：一组里只要有一个块是推算的，
    // 这组框就不能对外声称精确（混合时若按最好算，会给出假精度）。
    const precisions = g.blocks.map((b) => (b as { precision?: RectPrecision }).precision ?? rectPrecisionOf(b))
    const approx = precisions.some((p) => p !== 'exact')
    const veryApprox = precisions.length > 0 && precisions.every((p) => p === 'page')
    return { group: g, color, dashed, approx, veryApprox }
  })

  return (
    <div className="pointer-events-none absolute inset-0">
      <svg
        data-engine-box-overlay
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
        preserveAspectRatio="none"
        aria-hidden
      >
        {entries.flatMap(({ group, color, dashed, approx, veryApprox }) =>
          group.blocks.map((b, i) => {
            // 三档透明度：精确 1.0 / 推算 0.55 / 整页近似 0.28
            const stroke = !approx ? 1 : veryApprox ? 0.28 : 0.55
            return (
              <g key={`${group.variant.engine}:${i}`} data-engine-box={group.variant.engine}>
                <rect
                  x={b.rect.x * VIEWBOX}
                  y={b.rect.y * VIEWBOX}
                  width={b.rect.w * VIEWBOX}
                  height={b.rect.h * VIEWBOX}
                  fill={color}
                  fillOpacity={0.12}
                  stroke={color}
                  strokeOpacity={stroke}
                  strokeWidth={ENGINE_BOX_STROKE}
                  strokeDasharray={dashed ? ENGINE_BOX_DASH : undefined}
                  rx={2}
                />
                {/* 框旁标注：引擎短名 + 这个框对应的文本，律师一眼对上「哪个框是哪个引擎的哪个字」 */}
                <text
                  x={b.rect.x * VIEWBOX}
                  y={b.rect.y * VIEWBOX - 3}
                  fill={color}
                  fillOpacity={approx ? 0.7 : 1}
                  stroke="white"
                  strokeWidth={2.5}
                  paintOrder="stroke"
                  fontSize={11}
                >
                  {labelOf(group.variant.engine, b.text, approx)}
                </text>
              </g>
            )
          }),
        )}
      </svg>
    </div>
  )
}

/** 框旁小字：`MinerU 罗浩瑜`；文本过长截断，`approx` 补一个「≈」表示坐标不可信 */
function labelOf(engine: EngineName, text: string, approx: boolean): string {
  const body = text.trim().slice(0, 18)
  const name = engineShortLabel(engine)
  return `${approx ? '≈' : ''}${name}${body ? ` ${body}` : ''}`
}
