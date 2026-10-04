import { Check } from 'lucide-react'

import type { CalendarEvent } from '../api'
import { KIND_BADGE, KIND_LABEL } from '../constants'
import { isKeyKind, rangeLabel, summaryLine } from '../api-meta'
import { PANEL } from '../ui'
import { cn } from '@/lib/utils'
import { CardHead } from './CardHead'

interface TodayProps {
  events: CalendarEvent[]
  loading: boolean
  /** 拉取失败的可读文案（null = 正常）；失败时显示错误行而非「没有安排」假象 */
  error?: string | null
  /** 失败行的重试回调 */
  onRetry?: () => void
  onOpenEvent: (e: CalendarEvent) => void
  /** 勾选完成 / 取消完成（合并事件的全部成员由调用方统一处理） */
  onToggleComplete: (e: CalendarEvent) => void
}

/** 右栏「今日」：可勾选完成（落库，跨端同步），显示完成计数 */
export function TodayCard({ events, loading, error, onRetry, onOpenEvent, onToggleComplete }: TodayProps) {
  const total = events.length
  const doneCount = events.filter((e) => e.is_completed).length

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="今日" count={error ? '' : total ? `${total - doneCount} 件待办` : `${total} 件`} />
      <div className="px-2.5 pt-2 pb-3">
        {error && (
          <div className="px-2 py-6 text-center text-[12.5px] text-destructive">
            {error}
            {onRetry && (
              <button
                type="button"
                className="ml-1.5 cursor-pointer underline underline-offset-3"
                onClick={onRetry}
              >
                重试
              </button>
            )}
          </div>
        )}
        {!error && loading && <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>}
        {!error && !loading && total === 0 && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">今天没有安排，记一笔吧</div>
        )}
        {events.map((e) => {
          const isDone = e.is_completed
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
                onClick={() => onToggleComplete(e)}
                title={isDone ? '标记为未完成' : '标记为完成'}
                aria-label={isDone ? '标记为未完成' : '标记为完成'}
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
                  {isKeyKind(e.kind) && !isDone && <span className="text-[9.5px] font-semibold text-status-red">今日到期</span>}
                </div>
              </button>
            </div>
          )
        })}
      </div>
      <div className="flex justify-between border-t border-border px-3.5 py-[10px] text-[11px] text-muted-foreground">
        <span>
          已完成 <b className="font-semibold text-foreground tabular-nums">{doneCount}</b> / <b className="tabular-nums">{total}</b>
        </span>
        <span>点圆圈标记完成</span>
      </div>
    </section>
  )
}
