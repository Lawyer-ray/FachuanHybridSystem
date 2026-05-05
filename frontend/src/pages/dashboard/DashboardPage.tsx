import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Users, FileText, Briefcase, TrendingUp, ChevronLeft, ChevronRight, MapPin, User, Clock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PATHS } from '@/routes/paths'
import { clientApi } from '@/features/clients/api'
import { contractApi } from '@/features/contracts/api'
import { caseApi } from '@/features/cases/api'
import { reminderApi } from '@/features/reminders/api'
import type { Reminder, ReminderType } from '@/features/reminders/types'
import { formatDate } from '@/lib/date'

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

function useDashboardStats() {
  const clientsQuery = useQuery({ queryKey: ['dashboard-clients-count'], queryFn: () => clientApi.list(), staleTime: 60_000 })
  const contractsQuery = useQuery({ queryKey: ['dashboard-contracts-count'], queryFn: () => contractApi.list(), staleTime: 60_000 })
  const casesQuery = useQuery({ queryKey: ['dashboard-cases-count'], queryFn: () => caseApi.list(), staleTime: 60_000 })
  const now = new Date()
  const startDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
  const endDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()).padStart(2, '0')}`
  const financeQuery = useQuery({ queryKey: ['dashboard-finance', startDate, endDate], queryFn: () => contractApi.getFinanceStats({ start_date: startDate, end_date: endDate }), staleTime: 60_000 })
  return {
    clientCount: clientsQuery.data?.length ?? 0, contractCount: contractsQuery.data?.length ?? 0,
    caseCount: casesQuery.data?.length ?? 0, monthlyFee: financeQuery.data?.total_received_all ?? 0,
    isLoading: clientsQuery.isLoading || contractsQuery.isLoading || casesQuery.isLoading || financeQuery.isLoading,
  }
}

function mergeReminders(reminders: Reminder[]): Map<string, CalendarEvent[]> {
  const now = new Date()
  const map = new Map<string, CalendarEvent[]>()
  const hearingIndex = new Map<string, Map<string, CalendarEvent>>()
  for (const r of reminders) {
    if (!r.due_at) continue
    const dateKey = r.due_at.slice(0, 10)
    const time = r.due_at.slice(11, 16)
    const meta = (r.metadata ?? {}) as Record<string, unknown>
    const courtroom = typeof meta.courtroom === 'string' ? meta.courtroom : ''
    const lawyerName = typeof meta.lawyer_name === 'string' ? meta.lawyer_name : ''
    const location = typeof meta.location === 'string' ? meta.location : ''
    const sourceId = typeof meta.source_id === 'string' ? meta.source_id : ''
    const isOverdue = new Date(r.due_at) < now
    let mergeKey: string | null = null
    if (r.reminder_type === 'hearing') {
      mergeKey = sourceId ? `hearing:${sourceId}` : `hearing_fallback:${time}:${r.content}:${courtroom}:${r.contract ?? 0}:${r.case_log ?? 0}`
    }
    if (mergeKey) {
      if (!hearingIndex.has(dateKey)) hearingIndex.set(dateKey, new Map())
      const existing = hearingIndex.get(dateKey)!.get(mergeKey)
      if (existing) {
        if (lawyerName && !existing.lawyer_names.includes(lawyerName)) {
          existing.lawyer_names.push(lawyerName)
          existing.lawyer_name = existing.lawyer_names.join('、')
        }
        continue
      }
    }
    const event: CalendarEvent = {
      id: r.id, time, title: r.content, type_label: r.reminder_type_label, reminder_type: r.reminder_type,
      courtroom, location, lawyer_name: lawyerName, lawyer_names: lawyerName ? [lawyerName] : [],
      is_overdue: isOverdue, due_at: r.due_at, contract: r.contract, case_log: r.case_log,
    }
    if (!map.has(dateKey)) map.set(dateKey, [])
    map.get(dateKey)!.push(event)
    if (mergeKey) hearingIndex.get(dateKey)!.set(mergeKey, event)
  }
  for (const arr of map.values()) arr.sort((a, b) => a.time.localeCompare(b.time))
  return map
}

function EventDetailDialog({ event, open, onClose }: { event: CalendarEvent | null; open: boolean; onClose: () => void }) {
  if (!event) return null
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="text-base">{event.title}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className={TYPE_COLORS[event.reminder_type]}>{event.type_label}</Badge>
            <span className="text-muted-foreground flex items-center gap-1"><Clock className="size-3" />{formatDate(event.due_at)}</span>
            {event.is_overdue && <Badge variant="destructive" className="text-[10px]">已逾期</Badge>}
          </div>
          <div className="border-t pt-3 space-y-2">
            {event.lawyer_name && <div className="flex items-center gap-2 text-muted-foreground"><User className="size-3.5" /><span>承办律师: <span className="text-foreground font-medium">{event.lawyer_name}</span></span></div>}
            {event.courtroom && <div className="flex items-center gap-2 text-muted-foreground"><MapPin className="size-3.5" /><span>法庭: <span className="text-foreground">{event.courtroom}</span></span></div>}
            {event.location && <div className="flex items-center gap-2 text-muted-foreground"><MapPin className="size-3.5" /><span>地点: <span className="text-foreground">{event.location}</span></span></div>}
          </div>
          {(event.contract || event.case_log) && (
            <div className="border-t pt-3 text-xs text-muted-foreground">
              {event.contract && <div>关联合同 ID: {event.contract}</div>}
              {event.case_log && <div>关联案件日志 ID: {event.case_log}</div>}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CalendarCard() {
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear())
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth())
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const today = new Date()

  const { data: reminders } = useQuery({ queryKey: ['dashboard-reminders'], queryFn: () => reminderApi.list(), staleTime: 60_000 })
  const eventsByDate = useMemo(() => mergeReminders(reminders ?? []), [reminders])

  const weeks = useMemo(() => {
    const firstDay = new Date(viewYear, viewMonth, 1).getDay()
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
    const rows: (number | null)[][] = []
    let row: (number | null)[] = Array(firstDay).fill(null)
    for (let d = 1; d <= daysInMonth; d++) { row.push(d); if (row.length === 7) { rows.push(row); row = [] } }
    if (row.length > 0) { while (row.length < 7) row.push(null); rows.push(row) }
    return rows
  }, [viewYear, viewMonth])

  const prevMonth = () => { if (viewMonth === 0) { setViewMonth(11); setViewYear(viewYear - 1) } else setViewMonth(viewMonth - 1) }
  const nextMonth = () => { if (viewMonth === 11) { setViewMonth(0); setViewYear(viewYear + 1) } else setViewMonth(viewMonth + 1) }
  const goToday = () => { setViewYear(today.getFullYear()); setViewMonth(today.getMonth()) }

  const isToday = (d: number) => d === today.getDate() && viewMonth === today.getMonth() && viewYear === today.getFullYear()
  const dateKey = (d: number) => `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`

  const dayHeaders = ['日', '一', '二', '三', '四', '五', '六']

  return (
    <>
      <Card className="overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold tracking-tight">{viewYear}年{viewMonth + 1}月</span>
            <button
              onClick={goToday}
              className="text-xs text-muted-foreground hover:text-foreground border border-border rounded-md px-2 py-0.5 hover:bg-muted transition-colors"
            >
              今天
            </button>
          </div>
          <div className="flex items-center gap-0.5">
            <button onClick={prevMonth} className="size-7 flex items-center justify-center rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
              <ChevronLeft className="size-4" />
            </button>
            <button onClick={nextMonth} className="size-7 flex items-center justify-center rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>

        {/* Calendar grid */}
        <div className="grid grid-cols-7">
          {/* Day headers */}
          {dayHeaders.map((label, i) => (
            <div
              key={label}
              className={`text-center text-[11px] font-medium py-2 border-b border-r border-border ${i === 0 || i === 6 ? 'text-muted-foreground/60 bg-muted/30' : 'text-muted-foreground bg-muted/20'}`}
            >
              {label}
            </div>
          ))}

          {/* Day cells */}
          {weeks.map((row, ri) =>
            row.map((d, ci) => {
              const isWeekend = ci === 0 || ci === 6
              if (d === null) {
                return <div key={`${ri}-${ci}`} className="min-h-[110px] border-r border-b border-border bg-muted/5" />
              }
              const key = dateKey(d)
              const dayEvents = eventsByDate.get(key) ?? []
              const todayCell = isToday(d)

              return (
                <div
                  key={`${ri}-${ci}`}
                  className={`min-h-[110px] border-r border-b border-border p-1.5 align-top transition-colors ${
                    todayCell ? 'bg-accent/40' : isWeekend ? 'bg-muted/10' : 'hover:bg-muted/20'
                  }`}
                >
                  {/* Date number */}
                  <div className="flex items-center justify-between mb-1">
                    {todayCell ? (
                      <span className="inline-flex items-center justify-center size-6 rounded-full bg-foreground text-primary-foreground text-[11px] font-bold">
                        {d}
                      </span>
                    ) : (
                      <span className={`text-xs font-medium ${isWeekend ? 'text-muted-foreground/60' : 'text-muted-foreground'}`}>
                        {d}
                      </span>
                    )}
                    {dayEvents.length > 2 && (
                      <span className="text-[9px] text-muted-foreground bg-muted rounded px-1">{dayEvents.length}</span>
                    )}
                  </div>

                  {/* Events */}
                  <div className="space-y-0.5">
                    {dayEvents.slice(0, 2).map((ev) => (
                      <button
                        key={ev.id}
                        type="button"
                        onClick={() => setSelectedEvent(ev)}
                        className={`w-full text-left rounded-sm cursor-pointer transition-colors overflow-hidden border-l-2 ${
                          ev.is_overdue
                            ? 'border-l-destructive bg-destructive/5 hover:bg-destructive/10'
                            : 'border-l-foreground/20 bg-muted/40 hover:bg-muted/60'
                        }`}
                      >
                        <div className="px-1.5 py-1">
                          <div className="flex items-baseline gap-1">
                            <span className={`text-[9px] font-medium shrink-0 tabular-nums ${ev.is_overdue ? 'text-destructive' : 'text-muted-foreground'}`}>
                              {ev.time}
                            </span>
                            <span className="text-[10px] leading-tight truncate font-medium text-foreground/80">
                              {ev.title}
                            </span>
                          </div>
                          {ev.lawyer_name && (
                            <div className="text-[9px] leading-tight truncate pl-5 text-muted-foreground/70 mt-0.5">
                              {ev.lawyer_name}
                            </div>
                          )}
                        </div>
                      </button>
                    ))}
                    {dayEvents.length > 2 && (
                      <div className="text-[9px] text-muted-foreground text-center py-0.5">
                        +{dayEvents.length - 2} 更多
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 px-4 py-2 border-t border-border bg-muted/10 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-2 rounded-[2px] border-l-2 border-l-destructive bg-destructive/5" />
            <span>已逾期</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-2 rounded-[2px] border-l-2 border-l-foreground/20 bg-muted/40" />
            <span>待处理</span>
          </div>
        </div>
      </Card>

      <EventDetailDialog event={selectedEvent} open={!!selectedEvent} onClose={() => setSelectedEvent(null)} />
    </>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { clientCount, contractCount, caseCount, monthlyFee, isLoading } = useDashboardStats()

  const stats = useMemo(() => [
    { label: '当事人总数', value: isLoading ? '-' : String(clientCount), icon: <Users className="w-5 h-5" />, path: PATHS.ADMIN_CLIENTS },
    { label: '合同总数', value: isLoading ? '-' : String(contractCount), icon: <FileText className="w-5 h-5" />, path: PATHS.ADMIN_CONTRACTS },
    { label: '在办案件', value: isLoading ? '-' : String(caseCount), icon: <Briefcase className="w-5 h-5" />, path: PATHS.ADMIN_CASES },
    { label: '本月律师费', value: isLoading ? '-' : `¥${monthlyFee.toLocaleString()}`, icon: <TrendingUp className="w-5 h-5" />, path: PATHS.ADMIN_CONTRACTS },
  ], [clientCount, contractCount, caseCount, monthlyFee, isLoading])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">仪表盘</h1>
        <p className="text-sm text-muted-foreground mt-1">欢迎回来。以下是今日概览。</p>
      </div>
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => navigate(stat.path)}>
            <CardContent className="pt-4 pb-3 px-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[13px] text-muted-foreground">{stat.label}</span>
                <div className="text-muted-foreground">{stat.icon}</div>
              </div>
              <div className="text-2xl font-semibold">{stat.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <CalendarCard />
    </div>
  )
}
