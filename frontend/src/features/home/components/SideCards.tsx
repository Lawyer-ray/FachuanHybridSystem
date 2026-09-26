import { useCallback, useState } from 'react'
import { Check, Landmark, Loader2, Mail, Paperclip, Sparkles } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createReminder, listInbox, parseReminder } from '../api'
import { KIND_BADGE, KIND_LABEL } from '../constants'
import { isKeyKind } from '../api-meta'
import { rangeLabel, summaryLine } from '../api-meta'
import type { CalendarEvent } from '../api'
import type { InboxItem } from '../types'
import { BTN_PRIMARY, COUNT_PILL, PANEL } from '../ui'
import { cn } from '@/lib/utils'

/* ============================================================ 今日安排 */

interface TodayProps {
  events: CalendarEvent[]
  loading: boolean
  onOpenEvent: (e: CalendarEvent) => void
}

/** 右栏「今日」：可勾选完成，显示完成计数 */
export function TodayCard({ events, loading, onOpenEvent }: TodayProps) {
  const [done, setDone] = useState<Set<number>>(new Set())
  const total = events.length

  const toggle = (id: number) =>
    setDone((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="今日" count={`${total} 件`} action="全部日程 →" />
      <div className="px-2.5 pt-2 pb-3">
        {loading && <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>}
        {!loading && total === 0 && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">今天没有安排，记一笔吧</div>
        )}
        {events.map((e) => {
          const isDone = done.has(e.id)
          // 今日卡的副标题：时段（若与开始时刻不同）+ 地点/律师 摘要
          const range = rangeLabel(e)
          const meta = summaryLine(e)
          const eventMeta = [range && range !== e.time ? range : '', meta].filter(Boolean).join(' · ')
          return (
            <div
              key={e.id}
              className={cn('group flex items-start gap-[11px] rounded-[10px] px-2 py-[9px] transition-colors hover:bg-secondary/50', isDone && 'opacity-60')}
            >
              <button
                type="button"
                onClick={() => toggle(e.id)}
                title={isDone ? '标记为未完成' : '标记为完成'}
                className={cn(
                  'mt-[2px] flex h-[17px] w-[17px] flex-none items-center justify-center rounded-full border-[1.5px] transition-colors',
                  isDone ? 'border-foreground bg-foreground text-background' : 'border-input text-transparent hover:border-ring/50',
                )}
              >
                <Check className="h-2.5 w-2.5" strokeWidth={3} />
              </button>
              <span className="min-w-[38px] pt-[1px] text-[10.5px] font-semibold tabular-nums text-secondary-foreground">{e.time}</span>
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpenEvent(e)}>
                <div className={cn('text-[12.5px] leading-[1.4] font-semibold', isDone && 'line-through')}>{e.title}</div>
                {eventMeta && <div className="mt-[1px] truncate text-[10.5px] text-muted-foreground">{eventMeta}</div>}
                <div className="mt-1.5 flex items-center gap-1.5">
                  <span className={cn('rounded-[5px] border px-[7px] py-[2px] text-[9.5px] font-semibold', KIND_BADGE[e.kind])}>
                    {KIND_LABEL[e.kind]}
                  </span>
                  {isKeyKind(e.kind) && <span className="text-[9.5px] font-semibold text-status-red">今日到期</span>}
                </div>
              </button>
            </div>
          )
        })}
      </div>
      <div className="flex justify-between border-t border-border px-3.5 py-[10px] text-[11px] text-muted-foreground">
        <span>
          已完成 <b className="font-semibold text-foreground tabular-nums">{done.size}</b> / <b className="tabular-nums">{total}</b>
        </span>
        <span>点圆圈标记完成</span>
      </div>
    </section>
  )
}

/* ============================================================ 待处理流入 */

interface InboxProps {
  onOpen: (item: InboxItem) => void
  onAction: (item: InboxItem) => void
}

/** 右栏「待处理」：收件箱流（法院短信 / 材料包 / 邮件） */
export function InboxCard({ onOpen, onAction }: InboxProps) {
  const queryClient = useQueryClient()
  const { data = [], isLoading } = useQuery({
    queryKey: ['home-inbox'],
    queryFn: () => listInbox(6),
    staleTime: 30_000,
  })
  const todoCount = data.filter((x) => x.status === '待处理').length

  // 让别处（如提交法院短信后）能刷新这里
  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: ['home-inbox'] }), [queryClient])

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="待处理" count={`${todoCount} 条`} action="收件箱 →" />
      <div className="px-2.5 pt-1.5 pb-2.5">
        {isLoading && <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>}
        {!isLoading && data.length === 0 && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">暂无待处理消息</div>
        )}
        {data.map((x) => (
          <div key={x.id} className="flex items-center gap-[11px] rounded-[10px] px-2 py-[10px] transition-colors hover:bg-secondary/50">
            <div
              className={cn(
                'flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border',
                x.hot ? 'border-status-red/30 bg-status-red-bg text-status-red' : 'border-border bg-secondary text-secondary-foreground',
              )}
            >
              <KindIcon kind={x.kind} />
            </div>
            <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(x)}>
              <div className="truncate text-[12.5px] leading-[1.4] font-semibold">{x.title}</div>
              <div className="mt-[1px] truncate text-[10.5px] text-muted-foreground">
                {x.sourceLabel} · {x.who} · {x.at}
              </div>
            </button>
            <div className="flex flex-none flex-col items-end gap-[5px]">
              <span
                className={cn(
                  'rounded-[99px] border px-2 py-[2px] text-[9.5px] font-semibold whitespace-nowrap',
                  x.status === '待处理'
                    ? 'border-status-red/30 bg-status-red-bg text-status-red'
                    : 'border-border bg-secondary text-muted-foreground',
                )}
              >
                {x.status}
              </span>
              <button
                type="button"
                className="rounded-[7px] border border-input bg-secondary px-2.5 py-[3px] text-[10.5px] font-semibold whitespace-nowrap text-foreground transition-colors hover:bg-foreground hover:text-background"
                onClick={() => {
                  onAction(x)
                  refresh()
                }}
              >
                {x.action}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function KindIcon({ kind }: { kind: InboxItem['kind'] }) {
  if (kind === 'sms') return <Landmark className="h-4 w-4" />
  if (kind === 'mail') return <Mail className="h-4 w-4" />
  return <Paperclip className="h-4 w-4" />
}

/* ============================================================ 快速记一笔 */

interface QuickAddProps {
  onAdded: () => void
}

/**
 * 快速记一笔：先调 /reminders/parse 尝试抽取日期与类型，抽得到就直接建；
 * 抽不到（后端是规则解析，不认「明天/下周五」这类相对时间）时给出可操作提示。
 */
export function QuickAdd({ onAdded }: QuickAddProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [parsing, setParsing] = useState(false)

  const submit = async () => {
    const v = text.trim()
    if (!v) {
      toast.info('先写一句，比如「2026-09-28 09:30 开庭 张某诉李某 借贷纠纷」')
      return
    }
    setBusy(true)
    setParsing(true)
    try {
      const parsed = await parseReminder(v)
      if (parsed.length === 0) {
        toast.warning('没能识别出日期——请写具体日期，如「2026-09-28 09:30 开庭 …」')
        return
      }
      const p = parsed[0]
      await createReminder({
        reminder_type: p.reminder_type,
        content: p.content,
        due_at: p.due_at,
      })
      setText('')
      toast.success(`已加入日历：${p.reminder_type_label} · ${p.due_at.replace('T', ' ')}`)
      onAdded()
    } catch {
      toast.error('记一笔失败，请稍后重试')
    } finally {
      setBusy(false)
      setParsing(false)
    }
  }

  return (
    <div className="flex h-[42px] min-w-[320px] max-w-[480px] flex-1 items-center gap-[7px] rounded-[11px] border border-input bg-card py-0 pr-[5px] pl-[13px] shadow-[0_1px_2px_rgba(0,0,0,.03)] transition-colors focus-within:border-ring/40 md:ml-auto">
      {parsing ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />}
      <input
        className="min-w-0 flex-1 border-none bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void submit()
        }}
        placeholder="快速记一笔：2026-09-28 09:30 开庭 张某诉李某 借贷纠纷"
      />
      <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        记一笔
      </button>
    </div>
  )
}

/* ============================================================ 面板标题 */

function CardHead({ title, count, action }: { title: string; count: string; action: string }) {
  return (
    <div className="flex items-center gap-2.5 px-4 pt-[15px] pb-1">
      <b className="text-[13.5px] font-semibold">{title}</b>
      <span className={COUNT_PILL}>{count}</span>
      <span className="flex-1" />
      <span className="cursor-pointer rounded-[7px] px-[9px] py-[3px] text-[11px] text-muted-foreground transition-colors hover:bg-secondary">
        {action}
      </span>
    </div>
  )
}
