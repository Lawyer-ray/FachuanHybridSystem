/**
 * CaseLogSection - 案件日志列表区块
 *
 * Requirements: 3.8, 5.7
 */

import { useMemo, useState } from 'react'
import { FileText, Paperclip, Bell, Clock, Plus, Trash2, Loader2 } from 'lucide-react'
import { format } from 'date-fns'
import { toast } from 'sonner'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

import { useLogMutations } from '../hooks/use-log-mutations'
import type { CaseLog } from '../types'

export interface CaseLogSectionProps {
  logs: CaseLog[]
  editable?: boolean
  caseId?: number
}

const MAX_CONTENT_LENGTH = 120

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd HH:mm')
  } catch {
    return dateStr
  }
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '…'
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

  const mutations = caseId ? useLogMutations(caseId) : null

  const sortedLogs = useMemo(
    () => [...logs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [logs],
  )

  const handleAdd = () => {
    if (!mutations || !caseId || !newContent.trim()) return
    mutations.createLog.mutate(
      { case_id: caseId, content: newContent.trim() },
      {
        onSuccess: () => {
          toast.success('添加日志成功')
          setDialogOpen(false)
          setNewContent('')
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
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
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
                  <label className="text-sm font-medium">日志内容</label>
                  <textarea
                    className="border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 w-full rounded-md border px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] min-h-[100px] resize-y"
                    placeholder="请输入日志内容"
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={handleAdd}
                  disabled={!newContent.trim() || mutations?.createLog.isPending}
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
                <p className="text-sm leading-relaxed">
                  {truncate(log.content, MAX_CONTENT_LENGTH)}
                </p>
                {(attachCount > 0 || reminderCount > 0) && (
                  <div className="mt-2 flex items-center gap-3">
                    {attachCount > 0 && (
                      <Badge variant="outline" className="gap-1 text-xs">
                        <Paperclip className="size-3" />
                        {attachCount} 附件
                      </Badge>
                    )}
                    {reminderCount > 0 && (
                      <Badge variant="outline" className="gap-1 text-xs">
                        <Bell className="size-3" />
                        {reminderCount} 提醒
                      </Badge>
                    )}
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
