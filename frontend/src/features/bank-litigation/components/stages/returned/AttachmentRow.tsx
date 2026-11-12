/**
 * 回扫 —— 邮件抽屉里的一个附件。
 *
 * 折叠态是一行（文件名 / 归入槽位 / 大小 / 预览开关），点开后就地展开
 * 预览占位（图片与 PDF 都是占位框，演示不加载真实文件）。
 * 「展开没展开」只影响这一行，所以状态收在本组件里。
 */
import { FileImage, FileText } from 'lucide-react'
import { useState } from 'react'

import type { MailAttachment } from '../../demo-data'
import { Pill } from '../../ui'

/** 一个附件：折叠态是一行，点开就地展开预览（图片/PDF 占位） */
export function AttachmentRow({ attachment }: { attachment: MailAttachment }) {
  const [preview, setPreview] = useState(false)
  const Icon = attachment.kind === 'image' ? FileImage : FileText
  return (
    <div className="rounded-[8px] border border-border-light bg-card">
      <button
        type="button"
        aria-expanded={preview}
        onClick={() => setPreview((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left transition-colors hover:bg-secondary/40"
      >
        <Icon className="size-3.5 flex-none text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-[11px]">{attachment.name}</span>
        <Pill tone="neutral">{attachment.slot}</Pill>
        <span className="flex-none text-[10px] tabular-nums text-muted-foreground">{attachment.size}</span>
        <span className="flex-none text-[10px] text-status-blue">{preview ? '收起预览' : '预览'}</span>
      </button>
      {preview ? (
        <div className="border-t border-border-light px-2 py-2">
          <div className="flex h-[132px] items-center justify-center rounded-[6px] border border-dashed border-border bg-secondary/40">
            <div className="text-center">
              <Icon className="mx-auto size-5 text-muted-foreground" />
              <div className="mt-1 text-[10.5px] text-muted-foreground">
                {attachment.kind === 'image' ? '图片预览占位' : 'PDF 首页预览占位'}
              </div>
              <div className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">
                {attachment.pages} 页 · 第 1 页 / {attachment.pages}
              </div>
            </div>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span>识别结果：{attachment.slot}</span>
            <span className="ml-auto text-status-blue">下载原件</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
