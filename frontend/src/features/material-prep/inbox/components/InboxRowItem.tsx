import { memo, useState } from 'react'
import { FileText, Mail, MessageSquare, PackageCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import { friendlyTime } from '@/lib/format'
import { SOURCE_BADGE, SOURCE_LABEL, UNREAD_ACCENT, rowSubtitle } from '../constants'
import { canConvert, isPackSource, type InboxRow } from '../types'
import { useAttachmentPreview } from '../hooks/use-attachment-preview'
import { AttachmentCountButton, AttachmentStrip } from './AttachmentPeek'
import { AttachmentPreview } from './AttachmentPreview'

/** 来源类型 → 行首图标（法院类用印章感的 Mail / 短信气泡，材料包用盒子） */
function SourceIcon({ row }: { row: InboxRow }) {
  const cls = 'h-4 w-4'
  if (isPackSource(row)) return <FileText className={cls} aria-hidden />
  if (row.source_type === 'court_sms') return <MessageSquare className={cls} aria-hidden />
  return <Mail className={cls} aria-hidden />
}

/**
 * 收件箱单行。
 *
 * 视觉四要素：未读色条（左）、来源徽章 + 主题（中）、附件小样 + 时间（右）。
 * 未读用左侧 2px 竖条而不是整行变色——整行变色在长列表里太吵，而竖条
 * 扫一眼即可定位到哪几条没看。
 *
 * ## 为什么这一行不再是 `<button>`
 *
 * 行内要放**真按钮**（预览附件、展开附件条）。`<button>` 里嵌 `<button>` 是非法
 * HTML：浏览器会把它拆开，键盘与读屏行为全乱。改成 `<li>` + 一个铺满整行的
 * 「拉伸按钮」（`absolute inset-0`）承担「打开详情」的主操作，行内的其他按钮
 * 用 `relative z-10` 浮在上面——这是不嵌套交互元素又能整行可点的标准做法。
 *
 * ## 为什么附件小样放在行内
 *
 * 收件箱里最难的判断是「这条要不要进材料预处理」，而扫描件的主题常常毫无
 * 信息（`Attached Image`、`1153_001.pdf`）。份数胶囊点开就预览第一份，
 * 多份时展开看全部——判断从「点进去看」变成「扫一眼」。
 */
export const InboxRowItem = memo(function InboxRowItem({
  row,
  active,
  onSelect,
}: {
  row: InboxRow
  /** 当前在右侧详情抽屉里打开的那条 */
  active: boolean
  onSelect: (row: InboxRow) => void
}) {
  const packSource = isPackSource(row)
  const converted = Boolean(row.converted_message_id)
  const convertible = canConvert(row)
  // 老后端 / 旧缓存里没有 attachments 字段时不至于整页崩掉
  const attachments = row.attachments ?? []
  const [expanded, setExpanded] = useState(false)
  const preview = useAttachmentPreview()

  const subject = row.subject || '(无主题)'
  const openPreview = (index: number) => preview.open({ messageId: row.id, subject, attachments, index })

  return (
    <li
      className={cn(
        'group relative flex w-full items-start gap-3 px-4 py-3 text-left transition-colors',
        active ? 'bg-secondary/70' : 'hover:bg-secondary/40',
        !row.is_read && 'font-medium',
      )}
    >
      {/* 整行主操作：打开右侧详情抽屉（不是预览——预览由份数胶囊承担） */}
      <button
        type="button"
        onClick={() => onSelect(row)}
        aria-label={`打开：${subject}`}
        className="absolute inset-0 z-0 cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-status-blue"
      />

      {/* 未读色条 */}
      {!row.is_read && (
        <span className={cn('absolute inset-y-2 left-0 w-[2px] rounded-full', UNREAD_ACCENT)} aria-hidden />
      )}

      <span
        className={cn(
          'mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border',
          row.is_read
            ? 'border-border bg-card text-muted-foreground'
            : 'border-status-blue/30 bg-status-blue-bg text-status-blue',
        )}
      >
        <SourceIcon row={row} />
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              'truncate text-[13px] leading-[1.35]',
              row.is_read ? 'text-foreground/85' : 'text-foreground',
              !row.is_read && 'font-semibold',
            )}
            title={subject}
          >
            {subject}
          </span>
          {converted && (
            <span className="flex flex-none items-center gap-0.5 rounded-[5px] border border-status-green/30 bg-status-green-bg px-1.5 py-px text-[10px] font-medium text-status-green">
              <PackageCheck className="h-2.5 w-2.5" aria-hidden />
              已转
            </span>
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <span
            className={cn(
              'flex-none rounded-[4px] border px-1 py-px text-[10px] font-medium',
              SOURCE_BADGE[row.source_type] ?? 'border-border bg-secondary text-secondary-foreground',
            )}
          >
            {SOURCE_LABEL[row.source_type] ?? row.source_name}
          </span>
          <span className="truncate" title={rowSubtitle(row)}>
            {rowSubtitle(row)}
          </span>
        </span>

        {expanded && attachments.length > 0 && (
          <AttachmentStrip messageId={row.id} attachments={attachments} onPreview={openPreview} />
        )}
      </span>

      <span className="flex flex-none flex-col items-end gap-1">
        <span className="text-[11px] text-muted-foreground">
          {friendlyTime(row.received_at, { fallback: row.received_at })}
        </span>
        <span className="flex items-center gap-1.5">
          {attachments.length > 0 ? (
            <AttachmentCountButton
              count={attachments.length}
              expandable={attachments.length > 1}
              expanded={expanded}
              onPreview={() => openPreview(0)}
              onToggleExpand={() => setExpanded((v) => !v)}
            />
          ) : (
            row.has_attachments && (
              // 后端说「有附件」但没带元信息（老数据 / 消息未同步完）：保留原提示，
              // 不给假的可点入口
              <span className="rounded-[4px] bg-secondary px-1 py-px text-[10px] text-secondary-foreground">
                {row.attachment_count} 附件
              </span>
            )
          )}
          {/* 可转但未转：给一个极简提示，不放大成按钮（行本身就是入口） */}
          {convertible && (
            <span className="rounded-[4px] border border-border px-1 py-px text-[10px] text-muted-foreground">
              可转材料包
            </span>
          )}
          {packSource && (
            <span className="rounded-[4px] border border-border px-1 py-px text-[10px] text-muted-foreground">
              材料包
            </span>
          )}
        </span>
      </span>

      {/* 预览弹窗：portal 到 body，放在行内只是为了让它跟着这一行的状态走 */}
      {preview.target && (
        <AttachmentPreview target={preview.target} onClose={preview.close} onSwitch={preview.select} />
      )}
    </li>
  )
})
