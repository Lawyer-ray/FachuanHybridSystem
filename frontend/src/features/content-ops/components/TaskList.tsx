import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Input } from '@/components/ui/input'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Loader2,
  Clock,
  CheckCircle2,
  XCircle,
  FileText,
  Search,
  RefreshCw,
  Trash2,
  Zap,
} from 'lucide-react'
import { useTaskList, useDeleteTask } from '../hooks/use-content-ops'
import { STATUS_LABEL, MODE_LABEL } from '../types'
import type { ContentTask, TaskStatus } from '../types'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { toast } from 'sonner'

interface TaskListProps {
  selectedTaskId: number | null
  onSelectTask: (taskId: number) => void
}

const STATUS_ICON: Record<TaskStatus, typeof Clock> = {
  pending: Clock,
  queued: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: XCircle,
}

const STATUS_VARIANT: Record<TaskStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  queued: 'secondary',
  running: 'default',
  completed: 'default',
  failed: 'destructive',
  cancelled: 'outline',
}

const FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

export function TaskList({ selectedTaskId, onSelectTask }: TaskListProps) {
  const { data: tasks, isLoading, refetch, isFetching } = useTaskList()
  const deleteTask = useDeleteTask()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  const filteredTasks = useMemo(() => {
    if (!tasks) return []
    let result = [...tasks]

    // Status filter
    if (statusFilter === 'active') {
      result = result.filter((t) => ['pending', 'queued', 'running'].includes(t.status))
    } else if (statusFilter !== 'all') {
      result = result.filter((t) => t.status === statusFilter)
    }

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (t) =>
          (t.source_title || '').toLowerCase().includes(q) ||
          (t.keyword || '').toLowerCase().includes(q) ||
          (t.case_summary || '').toLowerCase().includes(q),
      )
    }

    // Sort: active first, then by created_at desc
    result.sort((a, b) => {
      const aActive = ['pending', 'queued', 'running'].includes(a.status) ? 0 : 1
      const bActive = ['pending', 'queued', 'running'].includes(b.status) ? 0 : 1
      if (aActive !== bActive) return aActive - bActive
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

    return result
  }, [tasks, searchQuery, statusFilter])

  const handleDelete = (taskId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    deleteTask.mutate(taskId, {
      onSuccess: () => toast.success('任务已删除'),
      onError: () => toast.error('删除失败'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const activeCount = tasks?.filter((t) => ['pending', 'queued', 'running'].includes(t.status)).length ?? 0

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 搜索和筛选 */}
      <div className="space-y-2 pb-3 border-b shrink-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="搜索任务..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-7 pl-7 text-xs"
          />
        </div>
        <div className="flex gap-1 flex-wrap items-center">
          {FILTER_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={statusFilter === opt.value ? 'default' : 'ghost'}
              size="sm"
              className="h-6 px-2 text-[10px]"
              onClick={() => setStatusFilter(opt.value)}
            >
              {opt.label}
              {opt.value === 'active' && activeCount > 0 && (
                <Badge variant="secondary" className="ml-1 h-4 px-1 text-[9px]">
                  {activeCount}
                </Badge>
              )}
            </Button>
          ))}
          <div className="flex-1" />
          <span className="text-[10px] text-muted-foreground mr-1">
            {filteredTasks.length} 项
          </span>
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching} className="h-6 px-2">
            <RefreshCw className={cn('w-3 h-3', isFetching && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* 任务列表 */}
      <div className="flex-1 min-h-0 overflow-y-auto pt-3">
        {filteredTasks.length === 0 ? (
          <div className="text-center py-12 text-sm text-muted-foreground">
            {tasks && tasks.length > 0 ? '没有匹配的任务' : '暂无任务记录'}
          </div>
        ) : (
          <motion.div
            className="space-y-2 pr-1"
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.04 } },
            }}
          >
            {filteredTasks.map((task) => (
              <motion.div
                key={task.id}
                variants={{
                  hidden: { opacity: 0, x: 8 },
                  visible: { opacity: 1, x: 0 },
                }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                layout
              >
                <TaskCard
                  task={task}
                  isSelected={task.id === selectedTaskId}
                  onClick={() => onSelectTask(task.id)}
                  onDelete={handleDelete}
                  isDeleting={deleteTask.isPending}
                />
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>
    </div>
  )
}

function TaskCard({ task, isSelected, onClick, onDelete, isDeleting }: {
  task: ContentTask
  isSelected: boolean
  onClick: () => void
  onDelete: (taskId: number, e: React.MouseEvent) => void
  isDeleting: boolean
}) {
  const Icon = STATUS_ICON[task.status]
  const isActive = ['pending', 'queued', 'running'].includes(task.status)
  const canDelete = ['completed', 'failed', 'cancelled'].includes(task.status)

  return (
    <Card
      className={cn(
        'w-full max-w-full cursor-pointer transition-all hover:border-primary/30 overflow-hidden group',
        isSelected && 'border-primary/50 bg-primary/5',
      )}
      onClick={onClick}
    >
      <CardContent className="p-3 space-y-1.5 overflow-hidden">
        <div className="grid items-center gap-1.5 overflow-hidden" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }}>
          <div className="flex items-center gap-1.5 overflow-hidden min-w-0">
            {task.mode === 'search' ? (
              <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            )}
            <span className="text-sm font-medium truncate min-w-0">
              {task.source_title || task.keyword || (task.mode === 'direct' ? `直投内容 #${task.id}` : `任务 #${task.id}`)}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {canDelete && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                    disabled={isDeleting}
                  >
                    <Trash2 className="w-3 h-3 text-muted-foreground hover:text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>删除任务？</AlertDialogTitle>
                    <AlertDialogDescription>
                      任务 #{task.id} 的所有生成内容（文章、音频）将一并删除，此操作不可撤销。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction onClick={(e) => onDelete(task.id, e)}>
                      确认删除
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
            <Badge variant={STATUS_VARIANT[task.status]} className="text-[10px] px-1.5 py-0 h-4">
              <Icon className={cn('w-2.5 h-2.5 mr-0.5', isActive && 'animate-spin')} />
              {STATUS_LABEL[task.status]}
            </Badge>
          </div>
        </div>

        {isActive && (
          <div className="space-y-1 overflow-hidden">
            <Progress value={task.progress} className="h-1" />
            <p className="text-[10px] text-muted-foreground truncate">{task.message || '处理中...'}</p>
          </div>
        )}

        {task.status === 'failed' && task.error && (
          <p className="text-[10px] text-destructive overflow-hidden text-ellipsis whitespace-nowrap">{task.error}</p>
        )}

        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground overflow-hidden">
          <Badge variant="outline" className="text-[9px] h-4 px-1 gap-0.5">
            {task.mode === 'search' ? <Search className="w-2.5 h-2.5" /> : <Zap className="w-2.5 h-2.5" />}
            {MODE_LABEL[task.mode]}
          </Badge>
          <span className="text-muted-foreground/50">·</span>
          <span className="truncate">{formatDistanceToNow(new Date(task.created_at), { addSuffix: true, locale: zhCN })}</span>
        </div>
      </CardContent>
    </Card>
  )
}
