import { ExternalLink, X } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { KIND_BADGE, KIND_LABEL } from '../constants'
import type { CalendarEvent } from '../api'
import { formatCN, parseKey } from '../domain'
import { cn } from '@/lib/utils'

interface Props {
  event: CalendarEvent | null
  onClose: () => void
  /** 跳案件详情；没实现时给提示 */
  onOpenCase: (e: CalendarEvent) => void
}

/**
 * 日历事件详情弹窗。
 *
 * 日历格子高度有限，律师 / 案号 / 庭审方式这些次要信息放不下，
 * 点一下用弹窗完整展示。
 */
export function EventDetailDialog({ event, onClose, onOpenCase }: Props) {
  if (!event) return null

  const rows: { label: string; value: string; mono?: boolean }[] = []
  if (event.time_range && event.time_range !== event.time) {
    rows.push({ label: '时段', value: event.time_range })
  }
  if (event.place) rows.push({ label: event.kind === 'court' ? '法庭' : '地点', value: event.place })
  if (event.person) rows.push({ label: '律师', value: event.person })
  if (event.hearing_type) rows.push({ label: '方式', value: event.hearing_type })
  if (event.case_no) rows.push({ label: '案号', value: event.case_no, mono: true })
  if (event.target_name && event.target_name !== event.title) {
    rows.push({ label: event.target_type || '关联', value: event.target_name })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[440px] gap-0 p-0" showCloseButton={false}>
        {/* 头部：日期 + 类别胶囊 + 关闭 */}
        <DialogHeader className="flex-row items-start gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11.5px] text-muted-foreground">
              {formatCN(parseKey(event.day))} {event.time}
              {event.is_today ? ' · 今天' : ''}
            </div>
            <DialogTitle className="mt-1 text-[15px] leading-snug font-semibold">{event.title}</DialogTitle>
          </div>
          <span
            className={cn(
              'mt-[2px] flex-none rounded-[6px] border px-[8px] py-[2px] text-[10px] font-semibold',
              KIND_BADGE[event.kind],
            )}
          >
            {event.kind_label || KIND_LABEL[event.kind]}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1 -mt-1 flex-none rounded-[7px] p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </DialogHeader>

        {/* 详情行 */}
        <div className="px-5 py-4">
          {rows.length === 0 ? (
            <div className="py-2 text-[12.5px] text-muted-foreground">没有更多信息</div>
          ) : (
            <dl className="flex flex-col gap-2.5">
              {rows.map((r) => (
                <div key={r.label} className="flex items-baseline gap-3">
                  <dt className="w-[42px] flex-none text-[11.5px] text-muted-foreground">{r.label}</dt>
                  <dd className={cn('min-w-0 flex-1 text-[12.5px] leading-relaxed', r.mono && 'font-mono text-[11.5px]')}>
                    {r.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {/* 合并提示：同一庭审被多次同步 */}
          {event.members > 1 && (
            <div className="mt-4 rounded-[8px] border border-border bg-secondary/50 px-3 py-2 text-[11px] text-muted-foreground">
              同一庭审在系统里有 {event.members} 条同步记录，已合并展示（关联 reminder #{event.member_ids.join('、#')}）
            </div>
          )}

          {/* 跳案件 */}
          <button
            type="button"
            onClick={() => onOpenCase(event)}
            disabled={!event.case_id}
            className={cn(
              'mt-4 flex h-9 w-full items-center justify-center gap-1.5 rounded-[9px] text-[12.5px] font-semibold transition-opacity',
              event.case_id
                ? 'bg-foreground text-background hover:opacity-85'
                : 'cursor-not-allowed border border-border bg-secondary text-muted-foreground',
            )}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {event.case_id ? `打开案件 #${event.case_id}` : '未关联案件'}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
