import { memo } from 'react'
import { FileText, Loader2, Mail, MessageSquare, PackageCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import { friendlyTime } from '@/lib/format'
import { SOURCE_BADGE, SOURCE_LABEL, rowSubtitle } from '../constants'
import { canConvert, isPackSource, type InboxRow } from '../types'

/** 来源类型 → 行首图标（法院类用印章感的 Mail / 短信气泡，材料包用盒子） */
function SourceIcon({ row }: { row: InboxRow }) {
  const cls = 'h-4 w-4'
  if (isPackSource(row)) return <FileText className={cls} aria-hidden />
  if (row.source_type === 'court_sms') return <MessageSquare className={cls} aria-hidden />
  if (row.source_type === 'imap') return <Mail className={cls} aria-hidden />
  return <Mail className={cls} aria-hidden />
}

/**
 * 收件箱单行。
 *
 * 视觉三要素：未读色条（左）、来源徽章 + 主题（中）、附件数与时间（右）。
 * 未读用左侧 2px 竖条而不是整行变色——整行变色在长列表里太吵，而竖条
 * 扫一眼即可定位到哪几条没看。
 *
 * 已转材料包的行在右侧给一个「已转」小徽章：让律师知道这条不用再点
 * （否则会反复点进材料预处理找同一条）。
 */
export const InboxRowItem = memo(function InboxRowItem({
  row,
  active,
  converting,
  onSelect,
}: {
  row: InboxRow
  /** 当前在右侧详情抽屉里打开的那条 */
  active: boolean
  /** 该行正在转材料包（禁用重复点击并给转圈） */
  converting: boolean
  onSelect: (row: InboxRow) => void
}) {
  const packSource = isPackSource(row)
  const converted = Boolean(row.converted_message_id)
  const convertible = canConvert(row)

  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      className={cn(
        'group relative flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
        active ? 'bg-secondary/70' : 'hover:bg-secondary/40',
        !row.is_read && 'font-medium',
      )}
    >
      {/* 未读色条 */}
      {!row.is_read && <span className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-status-blue" aria-hidden />}

      <span
        className={cn(
          'flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border',
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
            title={row.subject}
          >
            {row.subject || '(无主题)'}
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
      </span>

      <span className="flex flex-none flex-col items-end gap-1">
        <span className="text-[11px] text-muted-foreground">
          {friendlyTime(row.received_at, { fallback: row.received_at })}
        </span>
        <span className="flex items-center gap-1.5">
          {row.has_attachments && (
            <span className="rounded-[4px] bg-secondary px-1 py-px text-[10px] text-secondary-foreground">
              {row.attachment_count} 附件
            </span>
          )}
          {converting && <Loader2 className="h-3 w-3 animate-spin text-status-blue" aria-hidden />}
          {/* 可转但未转：给一个极简提示，不放大成按钮（行本身就是入口） */}
          {convertible && !converting && (
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
    </button>
  )
})
