import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { loadPdfDocument, renderPdfPage } from '@/lib/pdf'
import { errMessage } from '@/lib/errors'
import { fetchAttachmentBytes } from '../../api'
import { attachmentKind } from '../domain'
import type { InboxAttachment } from '../types'

/** 渲染宽度（px）。画布按这个宽度画，显示尺寸交给 CSS 缩放——缩放不必重渲染。 */
const PREVIEW_RENDER_WIDTH = 1400

type PdfDoc = Awaited<ReturnType<typeof loadPdfDocument>>

/**
 * 单个附件的应用内预览：PDF 逐页渲染，位图直接显示，其余只说明「不能在线看」。
 *
 * ## 为什么不开新标签
 *
 * 旧入口是「换一次性票据 → `window.open`」。那对「真的要读这份文书」是合适的，
 * 但对**分诊**（一条条看过去判断要不要进预处理）是灾难：每看一份就离开列表，
 * 回来还要重新滚动定位，二十条消息要点四十次、切二十次标签。
 *
 * ## 为什么字节走 `fetchAttachmentBytes` 而不是票据 URL
 *
 * pdf.js 会按需发 Range 请求，而下载票据是**单次使用**的——第一个分片用完，
 * 后续请求全部 403，表现为「转圈转到死」。`fetchAttachmentBytes` 是带
 * `Authorization` 的一次性整份下载 + 进程内缓存，且**与阅读器共用同一缓存键**
 * （`messageId:partIndex`）：在这里看过一眼，进阅读器就不用再下一次。
 *
 * ## 为什么 canvas 用 ref 直接挂
 *
 * 每页渲染出来的是一张 1400px 宽的位图，塞进 React state 会让整棵子树跟着
 * 重渲染；直接 `replaceChildren(canvas)` 只动这一个 DOM 节点（同 `PdfPageView`
 * 的做法）。
 */
export function AttachmentViewer({
  messageId,
  attachment,
  page,
  zoom = 1,
  onDocLoaded,
}: {
  messageId: number
  attachment: InboxAttachment
  /** 1 起的页码（仅 PDF 有效） */
  page: number
  /** 显示缩放倍数（1 = 适配宽度），只影响 CSS 尺寸，不触发重渲染 */
  zoom?: number
  /** PDF 加载完成回报总页数（父级据此画翻页控件） */
  onDocLoaded?: (numPages: number) => void
}) {
  const partIndex = attachment.part_index
  const kind = attachmentKind(attachment)

  const hostRef = useRef<HTMLDivElement | null>(null)
  const [doc, setDoc] = useState<PdfDoc | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(kind !== 'other')
  const [error, setError] = useState<string | null>(null)

  // 取字节 → 按类型转为 pdf.js 文档或图片 object URL
  useEffect(() => {
    if (kind === 'other') {
      setLoading(false)
      setDoc(null)
      setImageUrl(null)
      setError(null)
      return
    }

    let alive = true
    let objectUrl: string | null = null
    setLoading(true)
    setError(null)
    setDoc(null)
    setImageUrl(null)

    fetchAttachmentBytes(messageId, partIndex)
      .then(async (bytes) => {
        if (!alive) return
        if (kind === 'image') {
          objectUrl = URL.createObjectURL(new Blob([bytes], { type: attachment.content_type || 'image/*' }))
          setImageUrl(objectUrl)
          setLoading(false)
          return
        }
        // 与阅读器同键：两边看同一份附件只加载一次
        const loaded = await loadPdfDocument(`${messageId}:${partIndex}`, bytes)
        if (!alive) return
        setDoc(loaded)
        setLoading(false)
        onDocLoaded?.(loaded.numPages)
      })
      .catch((e: unknown) => {
        if (!alive) return
        setLoading(false)
        setError(errMessage(e, '附件读取失败'))
      })

    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
    // onDocLoaded 故意不进依赖：父级每次渲染都可能传新函数，进依赖会把整份
    // PDF 重新加载一遍（这是本仓库踩过的「effect 依赖写成内联函数」类问题）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messageId, partIndex, kind, attachment.content_type])

  // 页码 / 缩放变化 → 重画当前页（重新挂 canvas，不重建文档）
  useEffect(() => {
    if (!doc) return
    const host = hostRef.current
    if (!host) return
    let cancelled = false
    renderPdfPage(doc, page, PREVIEW_RENDER_WIDTH)
      .then((canvas) => {
        if (cancelled) return
        canvas.className = 'mx-auto block h-auto max-w-full rounded-[4px] bg-white shadow-[0_1px_10px_rgba(0,0,0,0.12)]'
        // 只有「换页」才换 canvas 内容：先清空避免旧页与骨架重叠
        host.replaceChildren(canvas)
      })
      .catch(() => {
        if (!cancelled) setError('这一页渲染失败，可能已超出文档页数')
      })
    return () => {
      cancelled = true
    }
  }, [doc, page])

  if (kind === 'other') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-[13px] font-medium text-foreground">该类型不支持在线预览</p>
        <p className="max-w-[320px] text-[12px] leading-relaxed text-muted-foreground">
          Word / Excel / 压缩包等附件在收件箱里只能下载后查看；PDF 与图片可以直接预览。
        </p>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full overflow-auto bg-secondary/40 p-3">
      {error && (
        <div className="flex h-full items-center justify-center px-6 text-center">
          <p className="text-[12.5px] text-status-red">{error}</p>
        </div>
      )}
      {!error && loading && (
        <div className="flex h-full items-center justify-center gap-2 text-[12.5px] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          正在读取附件…
        </div>
      )}
      {!error && !loading && imageUrl && (
        <img
          src={imageUrl}
          alt={attachment.filename}
          style={{ width: `${Math.round(zoom * 100)}%` }}
          className="mx-auto block h-auto max-w-none"
        />
      )}
      <div
        ref={hostRef}
        style={{ width: zoom === 1 ? undefined : `${Math.round(zoom * 100)}%` }}
        className={loading || error || imageUrl ? 'hidden' : undefined}
      />
    </div>
  )
}
