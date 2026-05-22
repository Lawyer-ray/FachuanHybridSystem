import { memo, useCallback, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, MapPin, User, Clock, Pencil, Trash2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { reminderApi } from '@/features/reminders/api'
import type { Reminder, ReminderType } from '@/features/reminders/types'
import { ReminderFormDialog } from '@/features/reminders/components/ReminderFormDialog'
import { useReminderMutations } from '@/features/reminders/hooks/use-reminder-mutations'
import { formatDate } from '@/lib/date'
import { AgendaView } from './AgendaView'

const DAY_HEADERS = ['日', '一', '二', '三', '四', '五', '六']

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

const TYPE_TEXT_COLORS: Record<ReminderType, { primary: string; secondary: string }> = {
  hearing: { primary: 'text-red-700 dark:text-red-400', secondary: 'text-red-600/70 dark:text-red-400/60' },
  asset_preservation_expires: { primary: 'text-orange-700 dark:text-orange-400', secondary: 'text-orange-600/70 dark:text-orange-400/60' },
  evidence_deadline: { primary: 'text-yellow-700 dark:text-yellow-400', secondary: 'text-yellow-600/70 dark:text-yellow-400/60' },
  appeal_deadline: { primary: 'text-purple-700 dark:text-purple-400', secondary: 'text-purple-600/70 dark:text-purple-400/60' },
  statute_limitations: { primary: 'text-pink-700 dark:text-pink-400', secondary: 'text-pink-600/70 dark:text-pink-400/60' },
  payment_deadline: { primary: 'text-blue-700 dark:text-blue-400', secondary: 'text-blue-600/70 dark:text-blue-400/60' },
  submission_deadline: { primary: 'text-cyan-700 dark:text-cyan-400', secondary: 'text-cyan-600/70 dark:text-cyan-400/60' },
  other: { primary: 'text-gray-700 dark:text-gray-400', secondary: 'text-gray-600/70 dark:text-gray-400/60' },
}

const OVERDUE_CHIP = 'bg-red-50 text-red-600 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-900/50'
const OVERDUE_TEXT = { primary: 'text-red-600 dark:text-red-400', secondary: 'text-red-500/70 dark:text-red-400/60' } as const

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
  case: number | null
  case_log: number | null
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
      is_overdue: isOverdue, due_at: r.due_at, contract: r.contract, case: r.case, case_log: r.case_log,
    }
    if (!map.has(dateKey)) map.set(dateKey, [])
    map.get(dateKey)!.push(event)
    if (mergeKey) hearingIndex.get(dateKey)!.set(mergeKey, event)
  }
  for (const arr of map.values()) arr.sort((a, b) => a.time.localeCompare(b.time))
  return map
}

function EventDetailDialog({
  event, open, onClose, onEdit, onDelete,
}: {
  event: CalendarEvent | null; open: boolean; onClose: () => void
  onEdit: (event: CalendarEvent) => void; onDelete: (event: CalendarEvent) => void
}) {
  if (!event) return null
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
        </button>
        <DialogHeader><DialogTitle className="text-base pr-6">{event.title}</DialogTitle></DialogHeader>
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
          {(event.contract || event.case || event.case_log) && (
            <div className="border-t pt-3 text-xs text-muted-foreground">
              {event.contract && <div>关联合同 ID: {event.contract}</div>}
              {event.case && <div>关联案件 ID: {event.case}</div>}
              {event.case_log && <div>关联案件日志 ID: {event.case_log}</div>}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button variant="outline" size="sm" onClick={() => onEdit(event)}>
            <Pencil className="size-3.5 mr-1.5" />编辑
          </Button>
          <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={() => onDelete(event)}>
            <Trash2 className="size-3.5 mr-1.5" />删除
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export const CalendarCard = memo(function CalendarCard() {
  const queryClient = useQueryClient()
  const { deleteMutation } = useReminderMutations()
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear())
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth())
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [formReminder, setFormReminder] = useState<Reminder | undefined>(undefined)
  const [formDate, setFormDate] = useState<Date | undefined>(undefined)
  const [deleteConfirm, setDeleteConfirm] = useState<CalendarEvent | null>(null)
  const [today] = useState(() => new Date())
  const [activeView, setActiveView] = useState<'month' | 'agenda'>('month')

  const { data: reminders } = useQuery({ queryKey: ['dashboard-reminders'], queryFn: () => reminderApi.list(), staleTime: 60_000 })
  const eventsByDate = useMemo(() => mergeReminders(reminders ?? []), [reminders])

  const { data: targetOptions } = useQuery({ queryKey: ['reminders-target-options'], queryFn: () => reminderApi.getTargetOptions(), staleTime: 300_000 })
  const contractOptions = useMemo(() => {
    const group = targetOptions?.groups.find(g => g.key === 'contract')
    return group?.items.map(i => ({ id: i.id, label: i.name })) ?? []
  }, [targetOptions])

  const weeks = useMemo(() => {
    const firstDay = new Date(viewYear, viewMonth, 1).getDay()
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
    const rows: (number | null)[][] = []
    let row: (number | null)[] = Array(firstDay).fill(null)
    for (let d = 1; d <= daysInMonth; d++) { row.push(d); if (row.length === 7) { rows.push(row); row = [] } }
    if (row.length > 0) { while (row.length < 7) row.push(null); rows.push(row) }
    return rows
  }, [viewYear, viewMonth])

  const prevMonth = useCallback(() => { if (viewMonth === 0) { setViewMonth(11); setViewYear(viewYear - 1) } else setViewMonth(viewMonth - 1) }, [viewMonth, viewYear])
  const nextMonth = useCallback(() => { if (viewMonth === 11) { setViewMonth(0); setViewYear(viewYear + 1) } else setViewMonth(viewMonth + 1) }, [viewMonth, viewYear])
  const goToday = useCallback(() => { const now = new Date(); setViewYear(now.getFullYear()); setViewMonth(now.getMonth()) }, [])

  const isToday = (d: number) => d === today.getDate() && viewMonth === today.getMonth() && viewYear === today.getFullYear()
  const dateKey = (d: number) => `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`

  const handleCreateForDate = useCallback((d: number) => {
    setFormMode('create')
    setFormReminder(undefined)
    setFormDate(new Date(viewYear, viewMonth, d, 9, 0))
    setFormOpen(true)
  }, [viewYear, viewMonth])

  const handleEditEvent = useCallback((event: CalendarEvent) => {
    const original = reminders?.find(r => r.id === event.id)
    if (!original) return
    setSelectedEvent(null)
    setFormMode('edit')
    setFormReminder(original)
    setFormDate(undefined)
    setFormOpen(true)
  }, [reminders])

  const handleDeleteEvent = useCallback((event: CalendarEvent) => {
    setSelectedEvent(null)
    setDeleteConfirm(event)
  }, [])

  const confirmDelete = () => {
    if (!deleteConfirm) return
    deleteMutation.mutate(deleteConfirm.id, {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['dashboard-reminders'] })
        setDeleteConfirm(null)
      },
    })
  }

  const handleFormSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-reminders'] })
  }

  return (
    <>
      <Card className="overflow-hidden">
        <Tabs value={activeView} onValueChange={(v) => setActiveView(v as 'month' | 'agenda')}>
          <div className="flex items-center justify-between px-5 py-3 border-b border-border/80">
            <div className="flex items-center gap-3">
              <span className="text-[15px] font-semibold tracking-tight">{viewYear}年{viewMonth + 1}月</span>
              <button
                onClick={goToday}
                className="text-xs text-muted-foreground hover:text-foreground border border-border/80 rounded-md px-2.5 py-1 hover:bg-muted/60 transition-colors"
              >
                今天
              </button>
              <TabsList className="h-7">
                <TabsTrigger value="month" className="text-xs px-2.5 py-0.5">月</TabsTrigger>
                <TabsTrigger value="agenda" className="text-xs px-2.5 py-0.5">议程</TabsTrigger>
              </TabsList>
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

          <TabsContent value="month" className="mt-0">
            <div className="grid grid-cols-7">
          {DAY_HEADERS.map((label, i) => (
            <div
              key={label}
              className={`text-center text-xs font-semibold py-2.5 border-b border-r border-border/80 ${i === 0 || i === 6 ? 'text-muted-foreground/50 bg-muted/20' : 'text-foreground/70 bg-muted/30'}`}
            >
              {label}
            </div>
          ))}

          {weeks.map((row, ri) =>
            row.map((d, ci) => {
              const isWeekend = ci === 0 || ci === 6
              if (d === null) {
                return <div key={`${ri}-${ci}`} className="min-h-[130px] border-r border-b border-border/60 bg-muted/5" />
              }
              const key = dateKey(d)
              const dayEvents = eventsByDate.get(key) ?? []
              const todayCell = isToday(d)

              return (
                <div
                  key={`${ri}-${ci}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleCreateForDate(d)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleCreateForDate(d) }}
                  className={`group min-h-[130px] border-r border-b border-border/60 p-1.5 align-top transition-colors cursor-pointer ${
                    todayCell
                      ? 'ring-2 ring-inset ring-primary z-10'
                      : isWeekend ? 'bg-muted/10 hover:bg-muted/20' : 'hover:bg-muted/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5 px-0.5">
                    <div className="flex items-center gap-0.5">
                      {todayCell ? (
                        <span className="inline-flex items-center justify-center size-6 rounded-full bg-primary text-primary-foreground text-xs font-bold">
                          {d}
                        </span>
                      ) : (
                        <span className={`text-xs font-semibold ${isWeekend ? 'text-muted-foreground/50' : 'text-foreground/70'}`}>
                          {d}
                        </span>
                      )}
                    </div>
                    {dayEvents.length > 0 && (
                      <span className="text-[10px] text-muted-foreground font-medium">{dayEvents.length}条</span>
                    )}
                  </div>

                  <div className="space-y-1">
                    {dayEvents.slice(0, 3).map((ev) => (
                      <button
                        key={ev.id}
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelectedEvent(ev) }}
                        className={`w-full text-left rounded-md cursor-pointer transition-colors overflow-hidden border ${
                          ev.is_overdue ? OVERDUE_CHIP : TYPE_COLORS[ev.reminder_type]
                        }`}
                      >
                        <div className="px-1.5 py-[5px]">
                          <div className="flex items-baseline gap-1.5">
                            <span className={`text-[11px] font-semibold shrink-0 tabular-nums ${ev.is_overdue ? OVERDUE_TEXT.primary : TYPE_TEXT_COLORS[ev.reminder_type].primary}`}>
                              {ev.time}
                            </span>
                            <span className={`text-[11px] leading-tight truncate font-medium ${ev.is_overdue ? OVERDUE_TEXT.primary : TYPE_TEXT_COLORS[ev.reminder_type].primary} ${ev.is_overdue ? 'line-through' : ''}`}>
                              {ev.title}
                            </span>
                          </div>
                          {(ev.lawyer_name || ev.courtroom) && (
                            <div className={`text-[10px] leading-tight truncate mt-0.5 ${ev.is_overdue ? OVERDUE_TEXT.secondary : TYPE_TEXT_COLORS[ev.reminder_type].secondary}`}>
                              {[ev.lawyer_name, ev.courtroom].filter(Boolean).join(' · ')}
                            </div>
                          )}
                        </div>
                      </button>
                    ))}
                    {dayEvents.length > 3 && (
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            onClick={(e) => e.stopPropagation()}
                            className="w-full text-[10px] text-muted-foreground text-center py-0.5 font-medium hover:text-foreground transition-colors cursor-pointer"
                          >
                            共 {dayEvents.length} 条
                          </button>
                        </PopoverTrigger>
                        <PopoverContent
                          align="start"
                          side="bottom"
                          className="w-64 p-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ScrollArea className="max-h-60">
                            <div className="p-2 space-y-1">
                              {dayEvents.map(ev => (
                                <button
                                  key={ev.id}
                                  type="button"
                                  onClick={() => setSelectedEvent(ev)}
                                  className={`w-full text-left flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50 transition-colors cursor-pointer ${ev.is_overdue ? 'bg-red-50/50 dark:bg-red-950/20' : ''}`}
                                >
                                  <span className={`text-[11px] font-semibold tabular-nums shrink-0 ${ev.is_overdue ? OVERDUE_TEXT.primary : TYPE_TEXT_COLORS[ev.reminder_type].primary}`}>
                                    {ev.time}
                                  </span>
                                  <span className={`text-[11px] truncate ${ev.is_overdue ? 'line-through text-red-500 dark:text-red-400' : ''}`}>{ev.title}</span>
                                </button>
                              ))}
                            </div>
                          </ScrollArea>
                        </PopoverContent>
                      </Popover>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
          </TabsContent>

          <TabsContent value="agenda" className="mt-0">
            <AgendaView
              eventsByDate={eventsByDate}
              viewYear={viewYear}
              viewMonth={viewMonth}
              onEventClick={setSelectedEvent}
            />
          </TabsContent>
        </Tabs>

        <div className="flex items-center flex-wrap gap-x-4 gap-y-1.5 px-5 py-2.5 border-t border-border/80 bg-muted/10 text-[11px] text-muted-foreground">
          {[
            { type: 'hearing', label: '开庭', color: 'bg-red-100 border-red-200' },
            { type: 'asset_preservation_expires', label: '保全到期', color: 'bg-orange-100 border-orange-200' },
            { type: 'evidence_deadline', label: '举证到期', color: 'bg-yellow-100 border-yellow-200' },
            { type: 'appeal_deadline', label: '上诉到期', color: 'bg-purple-100 border-purple-200' },
            { type: 'statute_limitations', label: '诉讼时效', color: 'bg-pink-100 border-pink-200' },
            { type: 'payment_deadline', label: '缴费期限', color: 'bg-blue-100 border-blue-200' },
            { type: 'submission_deadline', label: '材料提交', color: 'bg-cyan-100 border-cyan-200' },
            { type: 'other', label: '其他', color: 'bg-gray-100 border-gray-200' },
          ].map(item => (
            <div key={item.type} className="flex items-center gap-1.5">
              <div className={`w-3 h-2.5 rounded-sm border ${item.color}`} />
              <span>{item.label}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5 ml-1">
            <div className="w-3 h-2.5 rounded-sm border border-border bg-muted opacity-50" />
            <span>已逾期</span>
          </div>
        </div>
      </Card>

      <EventDetailDialog
        event={selectedEvent}
        open={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
        onEdit={handleEditEvent}
        onDelete={handleDeleteEvent}
      />

      <ReminderFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        mode={formMode}
        reminder={formReminder}
        onSuccess={handleFormSuccess}
        contractOptions={contractOptions}
        initialDate={formDate}
      />

      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <button
            type="button"
            onClick={() => setDeleteConfirm(null)}
            className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
          <DialogHeader>
            <DialogTitle className="text-base">确认删除</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            确定要删除提醒「{deleteConfirm?.title}」吗？此操作不可撤销。
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setDeleteConfirm(null)}>取消</Button>
            <Button variant="destructive" size="sm" onClick={confirmDelete}>删除</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
})
