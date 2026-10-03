import { memo, useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, FileText } from 'lucide-react'
import { canvasToRetainedImg, loadPdfDocument, pdfRenderWidthFor, renderPdfPage } from '@/lib/pdf'
import { fetchAttachmentBytes } from '../../api'
import type { BundleMat } from '../../types'
import { cn } from '@/lib/utils'

export interface PageRect {
  x: number
  y: number
  w: number
  h: number
}

const MIN_DRAG = 0.018

export const PageCell = memo(function PageCell({
  messageId,
  mi,
  p,
  mat,
  pickActive,
  selModeActive,
  selected,
  marks = [],
  ocrRect,
  onPickPage,
  onOcrBox,
  onToggleSel,
  onContextMenu,
}: {
  messageId: number
  mi: number
  p: number
  mat: BundleMat
  pickActive?: boolean
  selModeActive?: boolean
  selected?: boolean
  marks?: { fi: number; rect: PageRect; label: string }[]
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
    const a = dragRef.current
    const rect: PageRect = {
      x: Math.min(a.x, cur.x),
      y: Math.min(a.y, cur.y),
      w: Math.abs(cur.x - a.x),
      h: Math.abs(cur.y - a.y),
    }
    if (rect.w > MIN_DRAG || rect.h > MIN_DRAG) movedRef.current = true
    rectRef.current = rect
    setDragRect(rect)
  }

  const onPointerUp = () => {
    if (!dragRef.current || !pickActive) return
    dragRef.current = null
    const rect = rectRef.current
    rectRef.current = null
    setDragRect(null)
    if (rect && (rect.w > MIN_DRAG || rect.h > MIN_DRAG)) {
      onOcrBox?.(mi, p, rect)
    } else if (!rect) {
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
      ref={boxRef}
      data-mi={mi}
      data-p={p}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onClick={onClick}
      onDragStart={stopProp}
      onContextMenu={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onContextMenu?.(e, mi, p)
      }}
      className={cn(
        'relative select-text rounded-[7px] border bg-card text-[12.5px] leading-[1.9] text-foreground shadow-[0_1px_3px_rgba(0,0,0,0.05),0_10px_26px_rgba(0,0,0,0.04)] transition-opacity',
        pickActive ? 'cursor-crosshair select-none' : selModeActive ? 'cursor-pointer' : 'cursor-default',
        selected && 'border-zinc-800 ring-2 ring-zinc-800/80',
        selModeActive && !selected && 'opacity-35',
        pickActive && !selected && 'border-amber-300/70 ring-1 ring-amber-300/50',
      )}
    >
      <PageBody messageId={messageId} p={p} mat={mat} />

      {/* 选页已选：右上角黑圆勾（原型 .rp.picked::after） */}
      {selected && (
        <span className="pointer-events-none absolute right-3 top-3 grid h-[22px] w-[22px] place-items-center rounded-full bg-zinc-900 text-[13px] font-bold leading-none text-white">
          ✓
        </span>
      )}

      <div className="flex items-center justify-between gap-2 rounded-b-[7px] border-t border-border/60 bg-card px-3 py-1.5 text-[11px] text-muted-foreground">
        <span className="truncate">{mat.customName || mat.n}</span>
        <span className="tabular-nums">
          第 {p} / {mat.pages} 页
        </span>
      </div>

      {/* 来源标注：采纳后的绿框 */}
      {marks.map((m) => (
        <div
          key={m.fi}
          className="pointer-events-auto absolute rounded-[3px] border-[1.5px] border-green-500/80"
          style={{ left: `${m.rect.x * 100}%`, top: `${m.rect.y * 100}%`, width: `${m.rect.w * 100}%`, height: `${m.rect.h * 100}%` }}
        >
          <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-green-600 px-1 text-[10px] leading-4 text-white">
            {m.label}
          </span>
        </div>
      ))}

      {/* OCR 拖出的框 */}
      {dragRect && (
        <div
          className="pointer-events-none absolute rounded-[3px] border-2 border-blue-500/90 bg-blue-500/10"
          style={{ left: `${dragRect.x * 100}%`, top: `${dragRect.y * 100}%`, width: `${dragRect.w * 100}%`, height: `${dragRect.h * 100}%` }}
        />
      )}

      {/* 待确认的 OCR 框 */}
      {ocrRect && (
        <div
          className="pointer-events-none absolute rounded-[3px] border-2 border-green-500 bg-blue-500/10"
          style={{ left: `${ocrRect.x * 100}%`, top: `${ocrRect.y * 100}%`, width: `${ocrRect.w * 100}%`, height: `${ocrRect.h * 100}%` }}
        >
          <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-zinc-800 px-1 text-[10px] leading-4 text-white opacity-0" />
        </div>
      )}
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

function PdfPageView({ messageId, partIndex, pageNum }: { messageId: number; partIndex: number; pageNum: number }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  // null = 尚未因宽度/DPR 变化强制重渲（首渲在渲染 effect 内自测容器宽）；
  // 有值 = 用户拉窗口/改列数/缩放/跨屏拖动后按新宽度重渲
  const [forcedWidth, setForcedWidth] = useState<number | null>(null)
  // 最近一次实际渲染用的位图宽度，供变化检测比较
  const renderedWidthRef = useRef(0)

  // 宽度变化（窗口拉宽/列数变化/缩放）→ 位图宽度显著变化时重渲。
  // 此前 effect 只依赖 [messageId, partIndex, pageNum]，位图宽度在挂载时
  // 定格——拉宽窗口或放大后小位图被 CSS 拉伸，越拉越糊。
  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      const w = pdfRenderWidthFor(host.clientWidth)
      const prev = renderedWidthRef.current
      if (!prev || Math.abs(w - prev) > prev * 0.12) setForcedWidth(w)
    })
    ro.observe(host)
    return () => ro.disconnect()
  }, [])

  // DPR 变化（窗口跨屏拖动）不改变 CSS 宽、不触发 ResizeObserver，单独监听
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia === 'undefined') return
    const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`)
    const onChange = () => {
      const host = hostRef.current
      setForcedWidth(pdfRenderWidthFor(host?.clientWidth ?? 900))
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    let cancelled = false
    setState('loading')
    async function run() {
      try {
        const bytes = await fetchAttachmentBytes(messageId, partIndex)
        const doc = await loadPdfDocument(`${messageId}:${partIndex}`, bytes)
        // 按实际显示宽 × DPR 渲染：固定 900 位图在 Retina 上被拉伸 ~2 倍，
        // 文字发虚（原生查看器清晰正是因为按屏幕物理像素足额采样）
        const host = hostRef.current
        const targetWidth = forcedWidth ?? pdfRenderWidthFor(host?.clientWidth ?? 900)
        renderedWidthRef.current = targetWidth
        const canvas = await renderPdfPage(doc, pageNum, targetWidth)
        if (cancelled) return
        if (!host) return
        // 页宽随列数/缩放收缩时，canvas 必须跟随容器等比缩放；
        // 否则固定内禀宽会把窄列撑爆，造成文字被横向压缩变形（"挤压"）
        canvas.style.width = '100%'
        canvas.style.height = 'auto'
        host.innerHTML = ''
        host.appendChild(canvas)
        setState('ready')
        // canvas 位图（~21MB/页）页面无法回收，92 页大包滚完会 ~1.9GB；
        // 编码成 WebP img 驻留（~250KB/页），浏览器可自动丢弃离屏解码位图
        const img = await canvasToRetainedImg(canvas)
        if (cancelled || !host.isConnected) return
        img.style.width = '100%'
        img.style.height = 'auto'
        host.innerHTML = ''
        host.appendChild(img)
      } catch {
        if (!cancelled) setState('error')
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [messageId, partIndex, pageNum, forcedWidth])

  return (
    <div className="relative w-full bg-white">
      {state === 'loading' && <SkeletonLines />}
      {state === 'error' && (
        <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
      )}
      {/* 无 max-w 上限：页宽治理在 layout.ts 的 fitPageWidth（缩放可超 900 允许横向滚动），
          这里再 clamp 会让 >100% 的缩放失效 */}
      <div ref={hostRef} className="mx-auto w-full" />
    </div>
  )
}

function PhotoPageView({ messageId, partIndex }: { messageId: number; partIndex: number }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let alive = true
    let objectUrl: string | null = null
    fetchAttachmentBytes(messageId, partIndex)
      .then((bytes) => {
        objectUrl = URL.createObjectURL(new Blob([bytes]))
        if (alive) setUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl) // 卸载后才回来：别漏 revoke
      })
      .catch(() => {
        // 加载失败要有可见反馈（与 PdfPageView 的 error 分支同款），不能静默吞掉
        if (alive) setError(true)
      })
    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [messageId, partIndex])

  if (error) {
    return (
      <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
    )
  }
  if (!url) {
    return (
      <div className="grid h-56 place-items-center bg-zinc-50 text-xs text-muted-foreground">
        <ImageIcon className="h-6 w-6" />
      </div>
    )
  }
  return <img src={url} alt="材料页" className="block h-auto w-full bg-white" />
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

function SkeletonLines() {
  return (
    <div className="mx-auto w-full animate-pulse space-y-3 p-5">
      <div className="h-3 w-2/5 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-3/4 rounded bg-zinc-200" />
      <div className="h-3 w-5/6 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-2/3 rounded bg-zinc-200" />
    </div>
  )
}
