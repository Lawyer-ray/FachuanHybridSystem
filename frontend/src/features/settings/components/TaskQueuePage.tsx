import { useState, useCallback, useRef } from 'react'
import { RefreshCw, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { taskQueueApi } from '../api'
import { useQueuedTasks, useCompletedTasks, useFailedTasks, useScheduledTasks } from '../hooks/use-tasks'
import { useQueryClient } from '@tanstack/react-query'

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 1) return '< 1s'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function truncate(str: string | null, len: number): string {
  if (!str) return '-'
  return str.length > len ? str.slice(0, len) + '...' : str
}

export function TaskQueuePage() {
  const [activeTab, setActiveTab] = useState('queue')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmMessage, setConfirmMessage] = useState('')
  const pendingActionRef = useRef<(() => Promise<void>) | null>(null)
  const queryClient = useQueryClient()

  const queued = useQueuedTasks()
  const completed = useCompletedTasks()
  const failed = useFailedTasks()
  const scheduled = useScheduledTasks()

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['task-queue'] })
  }, [queryClient])

  const showConfirm = useCallback((message: string, action: () => Promise<void>) => {
    setConfirmMessage(message)
    pendingActionRef.current = action
    setConfirmOpen(true)
  }, [])

  const handleConfirm = useCallback(async () => {
    setConfirmOpen(false)
    if (pendingActionRef.current) {
      await pendingActionRef.current()
      pendingActionRef.current = null
    }
  }, [])

  const handleDelete = useCallback(async (taskId: string) => {
    showConfirm('确定删除此任务？', async () => {
      await taskQueueApi.deleteTask(taskId)
      invalidateAll()
    })
  }, [showConfirm, invalidateAll])

  const handleDeleteSchedule = useCallback(async (scheduleId: number) => {
    showConfirm('确定删除此定时任务？', async () => {
      await taskQueueApi.deleteSchedule(scheduleId)
      invalidateAll()
    })
  }, [showConfirm, invalidateAll])

  const handleResubmit = useCallback(async (taskId: string) => {
    showConfirm('确定重新提交此任务？', async () => {
      await taskQueueApi.resubmitTask(taskId)
      invalidateAll()
    })
  }, [showConfirm, invalidateAll])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.every((id) => prev.has(id))
      if (allSelected) return new Set()
      return new Set(ids)
    })
  }, [])

  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size === 0) return
    showConfirm(`确定删除选中的 ${selectedIds.size} 个任务？`, async () => {
      await Promise.all([...selectedIds].map((id) => taskQueueApi.deleteTask(id)))
      setSelectedIds(new Set())
      invalidateAll()
    })
  }, [selectedIds, showConfirm, invalidateAll])

  const queueData = queued.data ?? []
  const completedData = completed.data ?? []
  const failedData = failed.data ?? []
  const scheduledData = scheduled.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">Task 队列</h1>
          <p className="text-muted-foreground text-sm mt-1">查看 django_q 异步任务的执行状态和定时调度</p>
        </div>
        <div className="flex gap-2">
          {selectedIds.size > 0 && (
            <Button variant="destructive" size="sm" onClick={handleBatchDelete}>
              <Trash2 className="mr-1.5 size-4" />
              删除选中 ({selectedIds.size})
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={invalidateAll}>
            <RefreshCw className="mr-1.5 size-4" />刷新
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v); setSelectedIds(new Set()) }}>
        <TabsList>
          <TabsTrigger value="queue">队列中 ({queueData.length})</TabsTrigger>
          <TabsTrigger value="success">成功 ({completedData.length})</TabsTrigger>
          <TabsTrigger value="failed">失败 ({failedData.length})</TabsTrigger>
          <TabsTrigger value="schedule">定时 ({scheduledData.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="queue">
          {queueData.length === 0 ? (
            <EmptyState icon="file" title="队列为空" description="当前没有等待执行的任务" />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40px]">
                      <input type="checkbox" checked={queueData.length > 0 && queueData.every((t) => selectedIds.has(t.id))} onChange={() => toggleSelectAll(queueData.map((t) => t.id))} />
                    </TableHead>
                    <TableHead className="w-[80px]">ID</TableHead>
                    <TableHead>任务名</TableHead>
                    <TableHead className="w-[80px]">分组</TableHead>
                    <TableHead>函数</TableHead>
                    <TableHead className="w-[160px]">创建时间</TableHead>
                    <TableHead className="w-[70px]">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {queueData.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell><input type="checkbox" checked={selectedIds.has(t.id)} onChange={() => toggleSelect(t.id)} /></TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.id}</TableCell>
                      <TableCell className="font-medium text-sm">{t.name || '-'}</TableCell>
                      <TableCell>{t.group ? <Badge variant="secondary" className="text-xs">{t.group}</Badge> : '-'}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-[280px]" title={t.func}>{truncate(t.func, 40)}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.created_at || '-'}</TableCell>
                      <TableCell>
                        <Button variant="outline" size="sm" className="h-7 text-xs text-status-red border-status-red hover:bg-status-red-bg" onClick={() => handleDelete(t.id)}>
                          <Trash2 className="size-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="success">
          {completedData.length === 0 ? (
            <EmptyState icon="file" title="没有成功的任务" description="暂无已完成的任务记录" />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40px]">
                      <input type="checkbox" checked={completedData.length > 0 && completedData.every((t) => selectedIds.has(t.id))} onChange={() => toggleSelectAll(completedData.map((t) => t.id))} />
                    </TableHead>
                    <TableHead className="w-[80px]">ID</TableHead>
                    <TableHead>任务名</TableHead>
                    <TableHead className="w-[80px]">分组</TableHead>
                    <TableHead>函数</TableHead>
                    <TableHead className="w-[160px]">开始时间</TableHead>
                    <TableHead className="w-[80px]">耗时</TableHead>
                    <TableHead className="w-[70px]">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {completedData.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell><input type="checkbox" checked={selectedIds.has(t.id)} onChange={() => toggleSelect(t.id)} /></TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.id}</TableCell>
                      <TableCell className="font-medium text-sm">{t.name || '-'}</TableCell>
                      <TableCell>{t.group ? <Badge variant="outline" className="text-xs">{t.group}</Badge> : '-'}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-[280px]" title={t.func}>{truncate(t.func, 40)}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.started_at || '-'}</TableCell>
                      <TableCell className="text-status-green font-medium text-sm">{formatDuration(t.duration)}</TableCell>
                      <TableCell>
                        <Button variant="outline" size="sm" className="h-7 text-xs text-status-red border-status-red hover:bg-status-red-bg" onClick={() => handleDelete(t.id)}>
                          <Trash2 className="size-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="failed">
          {failedData.length === 0 ? (
            <EmptyState icon="file" title="没有失败的任务" description="所有任务执行成功" />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40px]">
                      <input type="checkbox" checked={failedData.length > 0 && failedData.every((t) => selectedIds.has(t.id))} onChange={() => toggleSelectAll(failedData.map((t) => t.id))} />
                    </TableHead>
                    <TableHead className="w-[80px]">ID</TableHead>
                    <TableHead>任务名</TableHead>
                    <TableHead className="w-[80px]">分组</TableHead>
                    <TableHead>函数</TableHead>
                    <TableHead className="w-[160px]">开始时间</TableHead>
                    <TableHead>错误信息</TableHead>
                    <TableHead className="w-[120px]">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {failedData.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell><input type="checkbox" checked={selectedIds.has(t.id)} onChange={() => toggleSelect(t.id)} /></TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.id}</TableCell>
                      <TableCell className="font-medium text-sm">{t.name || '-'}</TableCell>
                      <TableCell>{t.group ? <Badge variant="outline" className="text-xs">{t.group}</Badge> : '-'}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-[280px]" title={t.func}>{truncate(t.func, 40)}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{t.started_at || '-'}</TableCell>
                      <TableCell className="text-status-red text-xs truncate max-w-[300px]" title={t.result ?? undefined}>{truncate(t.result, 50)}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleResubmit(t.id)}>重提交</Button>
                          <Button variant="outline" size="sm" className="h-7 text-xs text-status-red border-status-red hover:bg-status-red-bg" onClick={() => handleDelete(t.id)}>
                            <Trash2 className="size-3" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="schedule">
          {scheduledData.length === 0 ? (
            <EmptyState icon="file" title="没有定时任务" description="暂无定时调度配置" />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[60px]">ID</TableHead>
                    <TableHead>名称</TableHead>
                    <TableHead>函数</TableHead>
                    <TableHead className="w-[90px]">调度类型</TableHead>
                    <TableHead className="w-[60px]">重复</TableHead>
                    <TableHead className="w-[160px]">下次执行</TableHead>
                    <TableHead className="w-[160px]">上次执行</TableHead>
                    <TableHead className="w-[70px]">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scheduledData.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="text-muted-foreground text-sm">{s.id}</TableCell>
                      <TableCell className="font-medium text-sm">{s.name || '-'}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground truncate max-w-[280px]" title={s.func}>{truncate(s.func, 40)}</TableCell>
                      <TableCell><Badge variant="outline" className="text-xs">{s.schedule_type}</Badge></TableCell>
                      <TableCell className="text-sm">{s.repeats === -1 ? '永久' : s.repeats}</TableCell>
                      <TableCell className="text-sm">{s.next_run || '-'}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{s.last_run || '-'}</TableCell>
                      <TableCell>
                        <Button variant="outline" size="sm" className="h-7 text-xs text-status-red border-status-red hover:bg-status-red-bg" onClick={() => handleDeleteSchedule(s.id)}>
                          <Trash2 className="size-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认操作</AlertDialogTitle>
            <AlertDialogDescription>{confirmMessage}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirm}>确定</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default TaskQueuePage
