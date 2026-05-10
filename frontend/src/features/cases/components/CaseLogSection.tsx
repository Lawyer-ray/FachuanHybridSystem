import { useMemo, useState } from 'react'
import { FileText, Paperclip, Bell, Clock, Plus, Trash2, Loader2, Download } from 'lucide-react'
import { formatDate } from '@/lib/date'
import { resolveMediaUrl } from '@/lib/api'
import { toast } from 'sonner'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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

import { useLogMutations } from '../hooks/use-log-mutations'
import { type CaseLog, CASE_LOG_REMINDER_TYPE_LABELS } from '../types'

export interface CaseLogSectionProps {
  logs: CaseLog[]
  editable?: boolean
  caseId?: number
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <FileText className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无案件日志</p>
    </div>
  )
}

export function CaseLogSection({ logs, editable, caseId }: CaseLogSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newContent, setNewContent] = useState('')
  const [reminderType, setReminderType] = useState('')
  const [reminderTime, setReminderTime] = useState('')

  const mutations = useLogMutations(caseId ?? 0)

  const sortedLogs = useMemo(
    () => [...logs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [logs],
  )

  const resetForm = () => {
    setNewContent('')
    setReminderType('')
    setReminderTime('')
  }

  const handleAdd = () => {
    if (!caseId || !newContent.trim()) return
    const hasReminder = reminderType && reminderTime
    mutations.createLog.mutate(
      {
        case_id: caseId,
        content: newContent.trim(),
        ...(hasReminder ? { reminder_type: reminderType, reminder_time: reminderTime } : {}),
      },
      {
        onSuccess: () => {
          toast.success('添加日志成功')
          setDialogOpen(false)
          resetForm()
        },
        onError: (e) => toast.error(e.message || '添加失败'),
      },
    )
  }

  const handleDelete = (id: number) => {
    if (!mutations) return
    mutations.deleteLog.mutate(id, {
      onSuccess: () => toast.success('删除成功'),
      onError: (e) => toast.error(e.message || '删除失败'),
    })
  }

  return (
    <div className="space-y-3">
      {editable && caseId && (
        <div className="flex justify-end">
          <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm() }}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                <Plus className="mr-1 size-3" /> 添加日志
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>添加案件日志</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
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
                  disabled={!newContent.trim() || (reminderType && !reminderTime) || mutations?.createLog.isPending}
                >
                  {mutations?.createLog.isPending && <Loader2 className="mr-1 size-3 animate-spin" />}
                  确认
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      {sortedLogs.length === 0 ? (
        <EmptyState />
      ) : (
        sortedLogs.map((log) => {
          const actorName = log.actor_detail?.real_name || log.actor_detail?.username || '未知'
          const attachCount = log.attachments?.length ?? 0
          const reminderCount = log.reminders?.length ?? 0

          return (
            <Card key={log.id} className="gap-0 py-0">
              <CardHeader className="pb-0 pt-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="text-muted-foreground size-4 shrink-0" />
                    <span className="text-muted-foreground text-xs">{actorName}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                      <Clock className="size-3" />
                      <span className="text-xs">{formatDate(log.created_at)}</span>
                    </div>
                    {editable && caseId && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon-xs">
                            <Trash2 className="text-muted-foreground size-3" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent size="sm">
                          <AlertDialogHeader>
                            <AlertDialogTitle>确认删除</AlertDialogTitle>
                            <AlertDialogDescription>确定要删除这条日志吗？</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>取消</AlertDialogCancel>
                            <AlertDialogAction variant="destructive" onClick={() => handleDelete(log.id)}>
                              删除
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pb-4 pt-2">
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{log.content}</p>

                {/* Attachments with download links */}
                {attachCount > 0 && (
                  <div className="mt-3 space-y-1">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Paperclip className="size-3" />
                      <span>{attachCount} 附件</span>
                    </div>
                    <div className="ml-4 space-y-1">
                      {log.attachments?.map((att) => {
                        const url = att.media_url || att.file_path
                        return (
                          <div key={att.id} className="flex items-center gap-2 text-xs">
                            {url ? (
                              <a
                                href={resolveMediaUrl(url) ?? url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary hover:underline flex items-center gap-1"
                              >
                                <Download className="size-3" />
                                附件 #{att.id}
                              </a>
                            ) : (
                              <span className="text-muted-foreground">附件 #{att.id}</span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Reminders */}
                {reminderCount > 0 && (
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    {log.reminders?.map((r) => (
                      <Badge key={r.id} variant="outline" className="gap-1 text-xs">
                        <Bell className="size-3" />
                        {CASE_LOG_REMINDER_TYPE_LABELS[r.reminder_type as keyof typeof CASE_LOG_REMINDER_TYPE_LABELS]?.zh ?? r.reminder_type}
                        <span className="text-muted-foreground ml-1">{formatDate(r.due_at)}</span>
                        {r.is_completed && <span className="text-green-600 ml-1">✓</span>}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })
      )}
    </div>
  )
}

export default CaseLogSection
