import { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, Loader2, ZoomIn, ZoomOut } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/lib/format'
import { attachmentDisplayName, attachmentKind, attachmentPagesLabel } from '../domain'
import { useAttachmentOpener } from '../hooks/use-attachment-opener'
import type { AttachmentPreviewTarget } from '../hooks/use-attachment-preview'
import type { InboxAttachment } from '../types'
import { AttachmentThumb } from './AttachmentPeek'
import { AttachmentViewer } from './AttachmentViewer'

const ZOOM_STEPS = [1, 1.5, 2] as const

/**
 * 附件预览弹窗（应用内，不跳页）。
 *
 * 与「换票 + `window.open`」那条老路径的分工：这里服务**分诊**——一条条快速看
 * 过去，判断哪条要进材料预处理；真要精读/批注仍进材料预处理阅读器（那里的
 * 页面组件带 OCR、框选、切分）。所以本弹窗刻意只做四件事：看、翻页、缩放、下载。
 *
 * 三条不许违反的约束：
 * 1. **不标已读**。打开预览不等于「我看过这条消息了」——收件箱的未读是按消息
 *    算的，只看附件就把 185 条未读刷没，用户会以为消息在消失。
 * 2. **不触发拆解/OCR**。这里只画页，任何 pipeline 副作用都不该由「看一眼」引发。
 * 3. **不预取**。缩略图只加载当前消息的附件，且只在弹窗打开时加载。
 */
export function AttachmentPreview({
  target,
  onClose,
  onSwitch,
}: {
  target: AttachmentPreviewTarget
  onClose: () => void
  /** 切到第 index 份附件（多附件时的左侧栏 / 左右方向键） */
  onSwitch: (index: number) => void
}) {
  const attachment = target.attachments[target.index]
  const [page, setPage] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [zoomStep, setZoomStep] = useState(0)
  const opener = useAttachmentOpener(target.messageId)

  const isPdf = attachment ? attachmentKind(attachment) === 'pdf' : false
  const pageable = isPdf && numPages > 1
  const switchable = target.attachments.length > 1

  // 换附件 = 换文档：页码与总页数必须归零，否则会停在上一份的页码上空白一片
  useEffect(() => {
    setPage(1)
    setNumPages(0)
    setZoomStep(0)
  }, [target.index, target.messageId])

  const goPage = useCallback(
    (delta: number) => {
      setPage((current) => {
        const next = current + delta
        if (numPages > 0) return Math.min(Math.max(1, next), numPages)
        return Math.max(1, next)
      })
    },
    [numPages],
  )

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      // 左右键的语义按当前能力走：能翻页就翻页，否则（单页 / 图片）切附件
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        const delta = event.key === 'ArrowRight' ? 1 : -1
        if (pageable) {
          event.preventDefault()
          goPage(delta)
        } else if (switchable) {
          event.preventDefault()
          const next = target.index + delta
          if (next >= 0 && next < target.attachments.length) onSwitch(next)
        }
      }
    },
    [pageable, switchable, goPage, target.index, target.attachments.length, onSwitch],
  )

  return (
    <Dialog open onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent
        showCloseButton={false}
        className="flex h-[min(90vh,940px)] w-[min(1240px,96vw)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
        onKeyDown={onKeyDown}
      >
        <DialogTitle className="sr-only">附件预览：{attachment ? attachmentDisplayName(attachment) : '附件'}</DialogTitle>
        <DialogDescription className="sr-only">
          预览 {target.subject || '这条消息'} 的附件，可翻页、缩放与下载。
        </DialogDescription>

        <PreviewHeader
          subject={target.subject}
          attachment={attachment}
          onDownload={() => attachment && void opener.run(attachment.part_index, 'download')}
          downloading={opener.pending?.kind === 'download'}
          onClose={onClose}
        />

        <div className="flex min-h-0 flex-1">
          {switchable && (
            <PreviewRail
              messageId={target.messageId}
              attachments={target.attachments}
              activeIndex={target.index}
              onSelect={onSwitch}
            />
          )}
          <div className="min-w-0 flex-1">
            {attachment && (
              <AttachmentViewer
                messageId={target.messageId}
                attachment={attachment}
                page={page}
                zoom={ZOOM_STEPS[zoomStep]}
                onDocLoaded={setNumPages}
              />
            )}
          </div>
        </div>

        <footer className="flex flex-none items-center gap-3 border-t border-border px-4 py-2">
          <div className="flex items-center gap-1">
            <IconButton label="上一页" disabled={!pageable || page <= 1} onClick={() => goPage(-1)}>
              <ChevronLeft className="h-4 w-4" />
            </IconButton>
            <span className="min-w-[68px] text-center text-[11.5px] tabular-nums text-muted-foreground">
              {pageable ? `${page} / ${numPages}` : isPdf ? (numPages > 0 ? `共 ${numPages} 页` : '') : ''}
            </span>
            <IconButton label="下一页" disabled={!pageable || page >= numPages} onClick={() => goPage(1)}>
              <ChevronRight className="h-4 w-4" />
            </IconButton>
          </div>

          <div className="ml-auto flex items-center gap-1">
            <IconButton label="缩小" disabled={zoomStep === 0} onClick={() => setZoomStep((s) => Math.max(0, s - 1))}>
              <ZoomOut className="h-4 w-4" />
            </IconButton>
            <span className="text-[11px] tabular-nums text-muted-foreground">{Math.round((ZOOM_STEPS[zoomStep] ?? 1) * 100)}%</span>
            <IconButton
              label="放大"
              disabled={zoomStep >= ZOOM_STEPS.length - 1}
              onClick={() => setZoomStep((s) => Math.min(ZOOM_STEPS.length - 1, s + 1))}
            >
              <ZoomIn className="h-4 w-4" />
            </IconButton>
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  )
}

/** 头部：消息主题（小字，用来定位「这是哪一条」）+ 附件名 + 体积/页数 */
function PreviewHeader({
  subject,
  attachment,
  downloading,
  onDownload,
  onClose,
}: {
  subject: string
  attachment: InboxAttachment | undefined
  downloading: boolean
  onDownload: () => void
  onClose: () => void
}) {
  const name = attachment ? attachmentDisplayName(attachment) : '附件'
  const pages = attachment ? attachmentPagesLabel(attachment) : ''
  const meta = [attachment ? formatBytes(attachment.size) : '', pages].filter(Boolean).join(' · ')

  return (
    <header className="flex flex-none items-start gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        {subject && (
          <p className="truncate text-[11px] text-muted-foreground" title={subject}>
            {subject}
          </p>
        )}
        <h2 className="truncate text-[13.5px] font-semibold leading-snug" title={name}>
          {name}
        </h2>
        {meta && <p className="mt-0.5 text-[11px] text-muted-foreground">{meta}</p>}
      </div>

      <button
        type="button"
        onClick={onDownload}
        disabled={!attachment || downloading}
        className="flex h-7 flex-none items-center gap-1.5 rounded-[7px] border border-border px-2.5 text-[12px] text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
      >
        {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
        下载
      </button>
      <IconButton label="关闭预览" onClick={onClose}>
        <span className="text-[16px] leading-none">×</span>
      </IconButton>
    </header>
  )
}

/** 左侧附件栏：多附件时用来横向切换（缩略图 + 名字） */
function PreviewRail({
  messageId,
  attachments,
  activeIndex,
  onSelect,
}: {
  messageId: number
  attachments: InboxAttachment[]
  activeIndex: number
  onSelect: (index: number) => void
}) {
  return (
    <aside className="w-[188px] flex-none overflow-y-auto border-r border-border bg-secondary/20 p-2">
      <p className="px-1 pb-1.5 text-[10.5px] font-semibold text-muted-foreground">{attachments.length} 个附件</p>
      <ul className="space-y-1">
        {attachments.map((att, index) => (
          <li key={att.part_index}>
            <button
              type="button"
              onClick={() => onSelect(index)}
              aria-current={index === activeIndex}
              className={cn(
                'flex w-full items-center gap-2 rounded-[7px] border p-1.5 text-left transition-colors',
                index === activeIndex
                  ? 'border-foreground/25 bg-card'
                  : 'border-transparent hover:border-border hover:bg-card/70',
              )}
            >
              <AttachmentThumb messageId={messageId} attachment={att} width={160} className="h-10 w-8" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[11.5px] leading-tight" title={attachmentDisplayName(att)}>
                  {attachmentDisplayName(att)}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {attachmentPagesLabel(att) || formatBytes(att.size)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
    >
      {children}
    </button>
  )
}
