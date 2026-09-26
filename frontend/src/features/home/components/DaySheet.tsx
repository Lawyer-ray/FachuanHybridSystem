import { X } from 'lucide-react'

import { KIND_BADGE, KIND_LABEL } from '../constants'
import type { CalendarEvent } from '../api'
import { formatCN, parseKey } from '../domain'
import { rangeLabel } from '../api-meta'

interface Props {
  /** dateKey；null 表示关闭 */
  day: string | null
  today: string
  events: CalendarEvent[]
  onClose: () => void
  onOpenEvent: (e: CalendarEvent) => void
  onAdd: () => void
}

/** 手机端底部抽屉：展示某一天的全部安排（原型 .sheet） */
export function DaySheet({ day, today, events, onClose, onOpenEvent, onAdd }: Props) {
  const open = day != null

  return (
    <>
      <div
        className={`fixed inset-0 z-60 bg-foreground/40 backdrop-blur-[2px] transition-[opacity,visibility] duration-250 ${
          open ? 'visible opacity-100' : 'invisible opacity-0'
        }`}
        onClick={onClose}
      />
      <div
        className={`fixed inset-x-0 bottom-0 z-61 flex max-h-[72vh] flex-col rounded-t-[18px] bg-card shadow-[0_-12px_40px_rgba(0,0,0,.12)] transition-transform duration-300 ease-out ${
          open ? 'translate-y-0' : 'translate-y-[105%]'
        }`}
      >
        <div className="mx-auto mt-2.5 mb-1 h-1 w-10 flex-none rounded-sm bg-input" />
        <div className="flex flex-none items-center gap-2.5 border-b border-border px-[18px] pt-2 pb-2.5">
          <b className="text-[14px] font-semibold">
            {day ? formatCN(parseKey(day)) : ''}
            {day === today && <span className="ml-1 text-[11.5px] font-normal text-muted-foreground">· 今天</span>}
          </b>
          <span className="text-[11.5px] text-muted-foreground">
            {events.length ? `${events.length} 条安排` : '暂无安排'}
          </span>
          <button
            type="button"
            className="ml-auto cursor-pointer rounded-[7px] border border-input bg-card px-[11px] py-1 text-[11.5px] text-secondary-foreground"
            onClick={onAdd}
          >
            ＋ 新增
          </button>
          <button type="button" onClick={onClose} className="text-muted-foreground" aria-label="关闭">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-[18px] pb-5">
          {events.length === 0 && <div className="py-[30px] text-center text-[12.5px] text-muted-foreground">这一天没有安排，点「＋ 新增」记一笔</div>}
          {events.map((e) => {
            const range = rangeLabel(e)
            return (
              <button
                key={e.id}
                type="button"
                className="flex w-full cursor-pointer items-start gap-3 border-b border-border py-[13px] text-left last:border-b-0"
                onClick={() => onOpenEvent(e)}
              >
                <span className="w-[42px] flex-none pt-[2px] text-right text-[12px] font-semibold tabular-nums text-secondary-foreground">
                  {e.time}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-medium">{e.title}</span>
                  {/* 时段：与开始时刻不同才显示，避免「10:00 · 10:00-12:00」 */}
                  {range && range !== e.time && (
                    <span className="mt-[2px] block text-[11.5px] tabular-nums text-secondary-foreground">{range}</span>
                  )}
                  {e.place && <span className="mt-[2px] block text-[11.5px] text-secondary-foreground">{e.place}</span>}
                  {e.person && <span className="mt-[2px] block text-[11.5px] text-muted-foreground">律师：{e.person}</span>}
                  {e.hearing_type && (
                    <span className="mt-[2px] block text-[11.5px] text-muted-foreground">{e.hearing_type}</span>
                  )}
                  {e.case_no && (
                    <span className="mt-[2px] block font-mono text-[10.5px] text-muted-foreground">案号 {e.case_no}</span>
                  )}
                  <span className="mt-1.5 flex items-center gap-[7px]">
                    <span className={`rounded-[5px] border px-[7px] py-[2px] text-[9.5px] font-semibold ${KIND_BADGE[e.kind]}`}>
                      {KIND_LABEL[e.kind]}
                    </span>
                    <span className="text-[11px] text-muted-foreground">→ 打开案件 / 材料</span>
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </>
  )
}
