import { useMemo, useState } from 'react'
import { Search, Loader2, Plus, Clock, Paperclip, Bell, Trash2 } from 'lucide-react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatDate } from '@/lib/date'

import { caseApi } from '@/features/cases/api'
import {
  type CaseLog,
  CASE_LOG_REMINDER_TYPE_LABELS,
} from '@/features/cases/types'

function relativeDate(dt: string): string {
  const now = new Date()
  const d = new Date(dt.replace(/ /, 'T'))
  const diff = now.getTime() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days}天前`
  return dt.slice(0, 10)
}

function getReminderLabel(type: string): string {
  return CASE_LOG_REMINDER_TYPE_LABELS[
    type as keyof typeof CASE_LOG_REMINDER_TYPE_LABELS
  ]?.zh ?? type
}

export function LogsPage() {
  const [search, setSearch] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newCaseId, setNewCaseId] = useState('')
  const [newContent, setNewContent] = useState('')
  const [reminderType, setReminderType] = useState('')
  const [reminderTime, setReminderTime] = useState('')
  const [visibleGroups, setVisibleGroups] = useState(10)  // 客户端分页：初始显示 10 组

  const queryClient = useQueryClient()

  const { data: logs = [], isLoading } = useQuery<CaseLog[]>({
    queryKey: ['all-logs'],
    queryFn: () => caseApi.listAllLogs(),
    staleTime: 60 * 1000,
    placeholderData: keepPreviousData,
  })

  const { data: cases = [] } = useQuery({
    queryKey: ['cases-for-log'],
    queryFn: () => caseApi.list(),
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  })

  const createMutation = useMutation({
    mutationFn: (data: { case_id: number; content: string; reminder_type?: string; reminder_time?: string }) =>
      caseApi.createLog(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['all-logs'] })
      setDialogOpen(false)
      resetForm()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number | string) => caseApi.deleteLog(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['all-logs'] }),
  })

  const resetForm = () => {
    setNewCaseId('')
    setNewContent('')
    setReminderType('')
    setReminderTime('')
  }

  const handleAdd = () => {
    if (!newCaseId || !newContent.trim()) return
    const hasReminder = reminderType && reminderTime
    createMutation.mutate({
      case_id: Number(newCaseId),
      content: newContent.trim(),
      ...(hasReminder ? { reminder_type: reminderType, reminder_time: reminderTime } : {}),
    })
  }

  const caseNameMap = useMemo(() => {
    const map: Record<number, string> = {}
    for (const c of cases) map[c.id] = c.name
    return map
  }, [cases])

  const filtered = useMemo(() => {
    if (!search) return logs
    const q = search.toLowerCase()
    return logs.filter((log) => {
      const caseName = caseNameMap[log.case] ?? ''
      const actorName = log.actor_detail?.real_name || log.actor_detail?.username || '未知'
      return (
        log.content.toLowerCase().includes(q) ||
        caseName.toLowerCase().includes(q) ||
        actorName.toLowerCase().includes(q)
      )
    })
  }, [logs, search, caseNameMap])

  const grouped = useMemo(() => {
    const groups: Record<string, CaseLog[]> = {}
    for (const log of filtered) {
      const dateKey = (log.created_at ?? '').slice(0, 10)
      if (!dateKey) continue
      if (!groups[dateKey]) groups[dateKey] = []
      groups[dateKey].push(log)
    }
    return Object.entries(groups).sort(([a], [b]) => b.localeCompare(a))
  }, [filtered])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">日志</h1>
          <p className="text-muted-foreground text-sm mt-1">
            查看所有案件的操作日志和时间线
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm() }}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="mr-1.5 size-4" />
              添加日志
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>添加案件日志</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>选择案件</Label>
                <Select value={newCaseId} onValueChange={setNewCaseId}>
                  <SelectTrigger>
                    <SelectValue placeholder="请选择案件" />
                  </SelectTrigger>
                  <SelectContent>
                    {cases.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>日志内容</Label>
                <textarea
                  className="border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 w-full rounded-md border px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] min-h-[100px] resize-y"
                  placeholder="请输入日志内容"
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                />
              </div>
              <div className="border-t pt-4">
                <p className="text-xs font-medium text-muted-foreground mb-3">提醒设置（可选）</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label className="text-xs">提醒类型</Label>
                    <Select value={reminderType} onValueChange={setReminderType}>
                      <SelectTrigger>
                        <SelectValue placeholder="不设置提醒" />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(CASE_LOG_REMINDER_TYPE_LABELS).map(([key, label]) => (
                          <SelectItem key={key} value={key}>{label.zh}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs">提醒时间</Label>
                    <Input
                      type="datetime-local"
                      value={reminderTime}
                      onChange={(e) => setReminderTime(e.target.value)}
                      disabled={!reminderType}
                    />
                  </div>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm() }}>取消</Button>
              <Button
                onClick={handleAdd}
                disabled={!newCaseId || !newContent.trim() || (reminderType && !reminderTime) || createMutation.isPending}
              >
                {createMutation.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                确认
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
        <Input
          type="text"
          placeholder="搜索日志内容、案件名称、操作人..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Logs */}
      {grouped.length === 0 ? (
        <div className="rounded-lg border p-12 text-center text-muted-foreground text-sm">
          暂无日志
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.slice(0, visibleGroups).map(([dateKey, dateLogs]) => (
            <div key={dateKey}>
              <div className="sticky top-0 z-10 bg-background py-2 mb-3">
                <span className="text-xs font-medium text-muted-foreground">
                  {relativeDate(dateKey + ' 00:00:00') === dateKey
                    ? dateKey
                    : `${relativeDate(dateKey + ' 00:00:00')} · ${dateKey}`}
                </span>
              </div>
              <div className={`grid grid-cols-1 gap-2 ${dateLogs.length > 1 ? 'md:grid-cols-2' : ''}`}>
                {dateLogs.map((log) => {
                  const actorName =
                    log.actor_detail?.real_name ||
                    log.actor_detail?.username ||
                    '未知'
                  const caseName = caseNameMap[log.case] ?? '未知案件'
                  const attachCount = log.attachments?.length ?? 0

                  return (
                    <Card key={log.id} className="gap-0 py-0 overflow-hidden min-w-0">
                      <CardHeader className="pb-0 pt-3 px-4">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <Badge variant="secondary" className="text-[11px] shrink-0">
                              {caseName}
                            </Badge>
                            <span className="text-muted-foreground text-xs">{actorName}</span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div className="flex items-center gap-1 text-muted-foreground">
                                  <Clock className="size-3" />
                                  <span className="text-xs">{formatDate(log.created_at).slice(11)}</span>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent>创建时间：{formatDate(log.created_at)}</TooltipContent>
                            </Tooltip>
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon-xs">
                                      <Trash2 className="text-muted-foreground size-3" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>删除日志</TooltipContent>
                                </Tooltip>
                              </AlertDialogTrigger>
                              <AlertDialogContent size="sm">
                                <AlertDialogHeader>
                                  <AlertDialogTitle>确认删除</AlertDialogTitle>
                                  <AlertDialogDescription>确定要删除这条日志吗？</AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>取消</AlertDialogCancel>
                                  <AlertDialogAction variant="destructive" onClick={() => deleteMutation.mutate(log.id)}>
                                    删除
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="pb-3 pt-2 px-4 min-w-0">
                        <p className="text-sm leading-relaxed break-all">{log.content}</p>
                        {(attachCount > 0 || (log.reminders && log.reminders.length > 0)) && (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            {attachCount > 0 && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Badge variant="outline" className="gap-1 text-[11px]">
                                    <Paperclip className="size-3" />
                                    {attachCount} 附件
                                  </Badge>
                                </TooltipTrigger>
                                <TooltipContent>包含 {attachCount} 个附件</TooltipContent>
                              </Tooltip>
                            )}
                            {log.reminders?.map((r) => (
                              <Tooltip key={r.id}>
                                <TooltipTrigger asChild>
                                  <Badge variant="outline" className="gap-1 text-[11px]">
                                    <Bell className="size-3" />
                                    {getReminderLabel(r.reminder_type)}
                                    <span className="text-muted-foreground ml-1">{formatDate(r.due_at)}</span>
                                    {r.is_completed && <span className="text-green-600 ml-1">✓</span>}
                                  </Badge>
                                </TooltipTrigger>
                                <TooltipContent>
                                  提醒：{getReminderLabel(r.reminder_type)} · {formatDate(r.due_at)}
                                  {r.is_completed ? '（已完成）' : ''}
                                </TooltipContent>
                              </Tooltip>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}
          {visibleGroups < grouped.length && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setVisibleGroups((v) => v + 10)}
              >
                加载更多（还有 {grouped.length - visibleGroups} 组）
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default LogsPage
