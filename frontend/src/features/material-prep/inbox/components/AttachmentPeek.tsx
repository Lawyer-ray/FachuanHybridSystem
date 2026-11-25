import { ChevronDown, Paperclip } from 'lucide-react'

import { cn } from '@/lib/utils'
import { formatBytes } from '@/lib/format'
import { attachmentDisplayName, attachmentPagesLabel } from '../domain'
import { useAttachmentThumbnail } from '../hooks/use-attachment-thumbnail'
import type { InboxAttachment } from '../types'

/**
 * 行内「附件小样」的两件套：右侧的份数按钮 + 展开后的附件条。
 *
 * 为什么不是每行一个「预览」按钮：列表 200 行、每行一个按钮就是 200 个视觉噪音，
 * 而且按钮本身不回答「里面是什么」。真正的信息量在**文件名 + 页数 + 首页小图**，
 * 所以份数胶囊本身就是入口（一点就预览第一份），再多份时才给展开看全部。
 */

/** 份数胶囊：点击 = 预览第一份附件（收件箱里最常用的一次点击） */
export function AttachmentCountButton({
  count,
  expanded,
  expandable,
  onPreview,
  onToggleExpand,
}: {
  count: number
  expanded: boolean
  /** 多于一份时才给展开箭头——单份没有「展开看全部」的意义 */
  expandable: boolean
  onPreview: () => void
  onToggleExpand: () => void
}) {
  return (
    <span className="relative z-10 flex items-center gap-0.5">
      <button
        type="button"
        onClick={(event) => {
          // 行本身是「打开抽屉」的拉伸按钮：不拦住就会连带把消息标已读
          event.stopPropagation()
          onPreview()
        }}
        title={count > 1 ? `预览附件（共 ${count} 份，先看第一份）` : '预览附件'}
        aria-label={count > 1 ? `预览 ${count} 份附件中的第一份` : '预览附件'}
        className={cn(
          'flex items-center gap-0.5 rounded-[4px] px-1 py-px text-[10px] transition-colors',
          'bg-secondary text-secondary-foreground hover:bg-secondary/70 hover:text-foreground',
          'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-status-blue',
        )}
      >
        <Paperclip className="h-2.5 w-2.5" aria-hidden />
        {count} 附件
      </button>
      {expandable && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            onToggleExpand()
          }}
          aria-expanded={expanded}
          aria-label={expanded ? '收起附件列表' : '展开附件列表'}
          title={expanded ? '收起附件列表' : '展开附件列表'}
          className="flex h-4 w-4 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <ChevronDown className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')} aria-hidden />
        </button>
      )}
    </span>
  )
}

/**
 * 展开后的附件条：每份一张小样 + 文件名 + 页数，点谁预览谁。
 *
 * 横向滚动而不是换行：多份附件的材料包一眼就能横向扫完，行高固定，
 * 不会因为展开一条消息就把整页列表挤走样。
 */
export function AttachmentStrip({
  messageId,
  attachments,
  onPreview,
}: {
  messageId: number
  attachments: InboxAttachment[]
  onPreview: (index: number) => void
}) {
  return (
    <ul className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
      {attachments.map((att, index) => (
        <li key={att.part_index} className="flex-none">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onPreview(index)
            }}
            title={`预览 ${attachmentDisplayName(att)}`}
            className="group/att flex w-[196px] items-center gap-2 rounded-[7px] border border-border bg-card p-1.5 text-left transition-colors hover:border-foreground/25 hover:bg-secondary/40"
          >
            <AttachmentThumb messageId={messageId} attachment={att} className="h-9 w-7" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11.5px] leading-tight text-foreground/90">
                {attachmentDisplayName(att)}
              </span>
              <span className="mt-0.5 block text-[10px] text-muted-foreground">
                {attachmentPagesLabel(att) || formatBytes(att.size)}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

/**
 * 附件小样（服务端渲染的首页缩略图）。
 *
 * 行内附件条、抽屉附件清单、预览弹窗左侧栏三处共用同一份实现：尺寸靠 className
 * 传（同一张图在不同位置只差 CSS），不要各写一个「再渲染一遍」的版本。
 *
 * 加载中给脉冲占位、失败给「文件」字占位——<img> 断链的破图图标在密集列表里
 * 极刺眼，而且会让人以为附件坏了。
 */
export function AttachmentThumb({
  messageId,
  attachment,
  width = 120,
  className,
}: {
  messageId: number
  attachment: InboxAttachment
  /** 请求的服务端渲染宽度（px）：行内小样给 120 就够，越宽越贵 */
  width?: number
  className?: string
}) {
  const { url, state } = useAttachmentThumbnail(messageId, attachment.part_index, { width })
  return (
    <span
      className={cn(
        'flex flex-none items-center justify-center overflow-hidden rounded-[3px] border border-border bg-secondary/60',
        className,
      )}
    >
      {state === 'ready' && url ? (
        <img src={url} alt="" className="h-full w-full object-cover object-top" />
      ) : (
        <span className={cn('text-[8.5px] text-muted-foreground', state === 'loading' && 'animate-pulse')}>
          {state === 'loading' ? '…' : '文件'}
        </span>
      )}
    </span>
  )
}
