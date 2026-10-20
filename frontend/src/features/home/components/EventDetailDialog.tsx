import { useEffect, useState } from 'react'
import { Check, ExternalLink, Pencil, Trash2, X } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { CalendarEvent } from '../api'
import { formatCN, parseKey } from '../domain'
import { BTN_DANGER } from '../ui'
import { cn } from '@/lib/utils'
import { EventEditForm } from './EventEditForm'

interface Props {
  event: CalendarEvent | null
  onClose: () => void
  /** 编辑保存成功（父层 invalidate 日历缓存）；本弹窗随即退回详情态，数据经 invalidate 自动刷新 */
  onSaved: () => void
  /** 跳案件详情；没实现时给提示 */
  onOpenCase: (e: CalendarEvent) => void
  /** 勾选完成 / 取消完成（合并事件的全部成员由调用方统一处理） */
  onToggleComplete: (e: CalendarEvent) => void
  /** 删除（二次确认已在本组件内完成；合并事件的全部成员由调用方统一处理） */
  onDelete: (e: CalendarEvent) => void
}

/**
 * 日历事件详情弹窗。
 *
 * 日历格子高度有限，律师 / 案号 / 庭审方式这些次要信息放不下，
 * 点一下用弹窗完整展示。
 *
 * 删除确认做在**本弹窗内部原地进行**（点「删除此安排」后按钮区原地换成
 * 确认条），不再叠第二层 AlertDialog——两层弹窗叠加既挡内容又难看。
 *
 * 编辑入口只在 event.can_edit 时出现（后端按写权限算好：关联对象的同案
 * 同事可改、全局提醒仅创建人与管理员；合并事件是多条同步记录，不可编辑），
 * 口径同 can_delete——没权限的连按钮都不给，而不是点了才收到 403。
 */
export function EventDetailDialog({ event, onClose, onSaved, onOpenCase, onToggleComplete, onDelete }: Props) {
  // 删除二次确认与编辑态都是弹窗内原地切换（hooks 必须在 early return 之前）
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [editing, setEditing] = useState(false)
  // 换事件 / 关弹窗后重置：弹窗组件常驻（event=null 时只是不渲染内容），
  // 不重置的话上一条事件残留的确认条 / 编辑态会带到下一条上
  useEffect(() => {
    setConfirmingDelete(false)
    setEditing(false)
  }, [event?.id])
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

  // 编辑态下点遮罩 / ESC：先退回详情（保护已输入的内容），再点一次才关弹窗
  const handleDialogClose = () => {
    if (editing) {
      setEditing(false)
      return
    }
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => !open && handleDialogClose()}>
      <DialogContent className="max-w-[440px] gap-0 p-0" showCloseButton={false}>
        {/* 头部：日期时间 + 标题 + 关闭。不显示「庭期」这类类别词——
            所有开庭提醒都是庭期，等于废话；真有混合类型时看详情行也够 */}
        <DialogHeader className="flex-row items-start gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <DialogDescription className="text-[11.5px] text-muted-foreground">
              {formatCN(parseKey(event.day))} {event.time}
              {event.is_today ? ' · 今天' : ''}
            </DialogDescription>
            <DialogTitle className={cn('mt-1 text-[15px] leading-snug font-semibold', event.is_completed && 'text-muted-foreground line-through')}>
              {event.title}
            </DialogTitle>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1 -mt-1 flex-none rounded-[7px] p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </DialogHeader>

        {editing ? (
          <EventEditForm
            event={event}
            onSaved={() => {
              onSaved()
              setEditing(false)
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
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
                同一庭审在系统里有 {event.members} 条同步记录，已合并展示（关联 reminder #{(event.member_ids ?? []).join('、#')}）
              </div>
            )}

            {/* 勾选完成（合并事件的全部成员一起标记，见 eventReminderIds） */}
            <button
              type="button"
              onClick={() => onToggleComplete(event)}
              className={cn(
                'mt-4 flex h-9 w-full items-center justify-center gap-1.5 rounded-[9px] border text-[12.5px] font-semibold transition-colors',
                event.is_completed
                  ? 'border-border bg-secondary text-secondary-foreground hover:bg-secondary/70'
                  : 'border-foreground/20 bg-card text-foreground hover:border-foreground/40',
              )}
            >
              <span
                className={cn(
                  'flex h-[15px] w-[15px] items-center justify-center rounded-full border-[1.5px]',
                  event.is_completed ? 'border-foreground bg-foreground text-background' : 'border-current text-transparent',
                )}
              >
                <Check className="h-[9px] w-[9px]" strokeWidth={3} />
              </span>
              {event.is_completed ? '恢复为未完成' : '标记完成'}
            </button>

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

            {/* 编辑 / 删除：权限由后端 can_edit / can_delete 算好（谁建谁管）。
                编辑 = 描边按钮，删除 = 低调文字按钮（悬停才见红），并排一行放不下时各自全宽 */}
            {(event.can_edit || event.can_delete) && (
              <div className="mt-3 flex gap-2">
                {event.can_edit && (
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-[9px] border border-border text-[12px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    编辑
                  </button>
                )}
                {event.can_delete && (
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(true)}
                    className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-[9px] text-[12px] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除此安排
                  </button>
                )}
              </div>
            )}

            {/* 删除二次确认：原地展开的确认条（不叠第二层弹窗） */}
            {confirmingDelete && (
              <div className="mt-3 rounded-[9px] border border-destructive/30 bg-destructive/5 px-3.5 py-2.5">
                <p className="text-[12px] font-medium text-destructive">
                  {event.members > 1 ? `同一庭审的 ${event.members} 条同步记录会一起删除，` : ''}
                  删除后不可恢复。
                </p>
                <div className="mt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(false)}
                    className="flex h-[30px] items-center justify-center rounded-[7px] border border-border bg-card px-3 text-[12px] font-medium text-secondary-foreground transition-colors hover:bg-secondary"
                  >
                    取消
                  </button>
                  <button type="button" onClick={() => onDelete(event)} className={BTN_DANGER}>
                    删除
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
