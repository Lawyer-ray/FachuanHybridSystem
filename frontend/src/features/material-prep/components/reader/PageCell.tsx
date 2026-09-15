import { memo, useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, FileText } from 'lucide-react'
import { loadPdfDocument, renderPdfPage, PDF_RENDER_WIDTH } from '@/lib/pdf'
import { fetchAttachmentBytes } from '../../api'
import type { BundleMat } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 单个页面。PDF 用 pdf.js 真渲染到 canvas，图片用 blob 直显，office 画占位卡。
 * 用 React.memo + 稳定 props，避免整段状态变化时重渲每页。
 */
export const PageCell = memo(function PageCell({
  messageId,
  mi,
  p,
  mat,
  focused,
  onPickPage,
}: {
  messageId: number
  mi: number
  p: number
  mat: BundleMat
  focused: boolean
  onPickPage?: (mi: number, p: number) => void
}) {
  return (
    <div
      data-mi={mi}
      data-p={p}
      role="button"
      tabIndex={onPickPage ? 0 : -1}
      onClick={() => onPickPage?.(mi, p)}
      onKeyDown={(e) => {
        if (onPickPage && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onPickPage(mi, p)
        }
      }}
      className={cn(
        'relative rounded-[7px] border border-border/70 bg-card text-[12.5px] leading-[1.9] text-foreground shadow-[0_1px_3px_rgba(0,0,0,0.05),0_10px_26px_rgba(0,0,0,0.04)]',
        onPickPage && 'cursor-crosshair ring-amber-300',
        focused && 'ring-2 ring-amber-400',
      )}
    >
      <PageBody messageId={messageId} p={p} mat={mat} />
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 text-[11px] text-muted-foreground">
        <span className="truncate">{mat.customName || mat.n}</span>
        <span className="tabular-nums">
          第 {p} / {mat.pages} 页
        </span>
      </div>
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

function PhotoPageView({ messageId, partIndex }: { messageId: number; partIndex: number }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
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
