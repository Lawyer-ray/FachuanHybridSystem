import { useCallback, useState } from 'react'

import type { InboxAttachment } from '../types'

/** 当前正在预览的附件（null = 弹窗关闭） */
export interface AttachmentPreviewTarget {
  messageId: number
  /** 弹窗标题用：让人确认「看的是哪一条消息里的附件」 */
  subject: string
  attachments: InboxAttachment[]
  /** 当前附件在 `attachments` 里的下标 */
  index: number
}

function clampIndex(index: number, length: number): number {
  if (length <= 0) return 0
  return Math.max(0, Math.min(length - 1, Math.trunc(index) || 0))
}

/**
 * 附件预览弹窗的开关状态。
 *
 * 为什么提成 hook：收件箱**行内小样**与**抽屉附件清单**是两个入口，但打开的是
 * 同一个弹窗、同一套翻页/下载动作。各写一份 state 就会出现「抽屉能翻页、行内
 * 不能」这种漂移。谁要入口谁调 `open(...)`，弹窗本体只认 `target`。
 *
 * 空附件列表直接忽略：宁可什么都不发生，也不要弹一个只有「没有可预览的附件」
 * 的空窗——那会让用户以为功能坏了。
 */
export function useAttachmentPreview(): {
  target: AttachmentPreviewTarget | null
  open: (next: { messageId: number; subject?: string; attachments: InboxAttachment[]; index?: number }) => void
  close: () => void
  select: (index: number) => void
} {
  const [target, setTarget] = useState<AttachmentPreviewTarget | null>(null)

  const open = useCallback(
    (next: { messageId: number; subject?: string; attachments: InboxAttachment[]; index?: number }) => {
      if (!next.attachments.length) return
      setTarget({
        messageId: next.messageId,
        subject: next.subject ?? '',
        attachments: next.attachments,
        index: clampIndex(next.index ?? 0, next.attachments.length),
      })
    },
    [],
  )

  const close = useCallback(() => setTarget(null), [])

  const select = useCallback((index: number) => {
    setTarget((current) => (current ? { ...current, index: clampIndex(index, current.attachments.length) } : current))
  }, [])

  return { target, open, close, select }
}
