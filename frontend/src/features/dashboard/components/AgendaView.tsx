import { memo, useMemo } from 'react'
import { CalendarDays } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { ReminderType } from '@/features/reminders/types'

const TYPE_COLORS: Record<ReminderType, string> = {
  hearing: 'bg-red-100 text-red-700 border-red-200',
  asset_preservation_expires: 'bg-orange-100 text-orange-700 border-orange-200',
  evidence_deadline: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  appeal_deadline: 'bg-purple-100 text-purple-700 border-purple-200',
  statute_limitations: 'bg-pink-100 text-pink-700 border-pink-200',
  payment_deadline: 'bg-blue-100 text-blue-700 border-blue-200',
  submission_deadline: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  other: 'bg-gray-100 text-gray-700 border-gray-200',
}

interface CalendarEvent {
  id: number
  time: string
  title: string
  type_label: string
  reminder_type: ReminderType
  courtroom: string
  location: string
  lawyer_name: string
  lawyer_names: string[]
  is_overdue: boolean
  due_at: string
  contract: number | null
  case_log: number | null
}

const WEEKDAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export const AgendaView = memo(function AgendaView({
  eventsByDate, viewYear, viewMonth, onEventClick,
}: {
  eventsByDate: Map<string, CalendarEvent[]>
  viewYear: number
  viewMonth: number
  onEventClick: (event: CalendarEvent) => void
}) {
  const sortedEntries = useMemo(() => {
    const entries: { dateKey: string; date: Date; events: CalendarEvent[] }[] = []
    for (const [dateKey, events] of eventsByDate) {
      const [y, m, d] = dateKey.split('-').map(Number)
      if (y === viewYear && m - 1 === viewMonth) {
        entries.push({ dateKey, date: new Date(y, m - 1, d), events })
      }
    }
    entries.sort((a, b) => a.dateKey.localeCompare(b.dateKey))
    return entries
  }, [eventsByDate, viewYear, viewMonth])

  if (sortedEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <CalendarDays className="size-10 mb-3 opacity-40" />
        <p className="text-sm">本月暂无事件</p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-[460px]">
      <div className="divide-y divide-border/60">
        {sortedEntries.map(({ dateKey, date, events }) => (
          <div key={dateKey} className="px-4 py-3">
            <div className="text-xs font-semibold text-muted-foreground mb-2">
              {date.getMonth() + 1}月{date.getDate()}日 {WEEKDAY_NAMES[date.getDay()]}
            </div>
            <div className="space-y-1.5">
              {events.map(ev => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => onEventClick(ev)}
                  className="w-full text-left flex items-start gap-2.5 rounded-md px-2.5 py-2 hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <span className="text-xs font-semibold tabular-nums text-muted-foreground shrink-0 w-10 pt-0.5">
                    {ev.time}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Badge variant="outline" className={`text-[10px] px-1.5 py-0 font-medium ${TYPE_COLORS[ev.reminder_type]}`}>
                        {ev.type_label}
                      </Badge>
                      {ev.is_overdue && <Badge variant="destructive" className="text-[10px] px-1 py-0">逾期</Badge>}
                    </div>
                    <span className={`text-sm leading-tight ${ev.is_overdue ? 'line-through text-muted-foreground' : ''}`}>
                      {ev.title}
                    </span>
                    {(ev.lawyer_name || ev.courtroom) && (
                      <div className="text-xs text-muted-foreground mt-0.5 truncate">
                        {[ev.lawyer_name, ev.courtroom].filter(Boolean).join(' · ')}
                      </div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
})
