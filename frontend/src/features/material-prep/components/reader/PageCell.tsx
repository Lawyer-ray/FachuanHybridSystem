import { memo, useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, FileText } from 'lucide-react'
import { loadPdfDocument, renderPdfPage, PDF_RENDER_WIDTH } from '@/lib/pdf'
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
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const movedRef = useRef(false)
  const [dragRect, setDragRect] = useState<PageRect | null>(null)

  const stopProp = (e: React.SyntheticEvent) => e.stopPropagation()

  const onPointerDown = (e: React.PointerEvent) => {
    if (!pickActive || e.button !== 0) return
    const r = boxRef.current?.getBoundingClientRect()
    if (!r) return
    dragRef.current = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }
    movedRef.current = false
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
    setDragRect(rect)
  }

  const onPointerUp = () => {
    if (!dragRef.current || !pickActive) return
    dragRef.current = null
    const rect = dragRect
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

/** 选择页体渲染分支 */
function PageBody({ messageId, p, mat }: { messageId: number; p: number; mat: BundleMat }) {
  if (mat.k === 'pdf') return <PdfPageView messageId={messageId} partIndex={mat.partIndex} pageNum={p} />
  if (mat.k === 'photo') return <PhotoPageView messageId={messageId} partIndex={mat.partIndex} />
  return <OfficePlaceholder mat={mat} />
}

function PdfPageView({ messageId, partIndex, pageNum }: { messageId: number; partIndex: number; pageNum: number }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setState('loading')
    async function run() {
      try {
        const bytes = await fetchAttachmentBytes(messageId, partIndex)
        const doc = await loadPdfDocument(`${messageId}:${partIndex}`, bytes)
        const canvas = await renderPdfPage(doc, pageNum, PDF_RENDER_WIDTH)
        if (cancelled) return
        const host = hostRef.current
        if (!host) return
        host.innerHTML = ''
        host.appendChild(canvas)
        setState('ready')
      } catch {
        if (!cancelled) setState('error')
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [messageId, partIndex, pageNum])

  return (
    <div className="relative w-full bg-white">
      {state === 'loading' && <SkeletonLines />}
      {state === 'error' && (
        <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
      )}
      <div ref={hostRef} className="mx-auto w-full max-w-[900px]" />
    </div>
  )
}

// react-hooks lint shim (avoid rename churn)
// eslint-disable-next-line react-hooks/rules-of-hooks
import { useEffect as useEffect0 } from 'react'

function PhotoPageView({ messageId, partIndex }: { messageId: number; partIndex: number }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect0(() => {
    let alive = true
    let objectUrl: string | null = null
    fetchAttachmentBytes(messageId, partIndex)
      .then((bytes) => {
        objectUrl = URL.createObjectURL(new Blob([bytes]))
        if (alive) setUrl(objectUrl)
      })
      .catch(() => {})
    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [messageId, partIndex])

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
    <div className="mx-auto w-full max-w-[900px] animate-pulse space-y-3 p-5">
      <div className="h-3 w-2/5 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-3/4 rounded bg-zinc-200" />
      <div className="h-3 w-5/6 rounded bg-zinc-200" />
      <div className="h-3 w-full rounded bg-zinc-200" />
      <div className="h-3 w-2/3 rounded bg-zinc-200" />
    </div>
  )
}
