import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import {
  Loader2,
  Clock,
  CheckCircle2,
  XCircle,
  FileText,
  Search,
  RefreshCw,
} from 'lucide-react'
import { useTaskList } from '../hooks/use-content-ops'
import { STATUS_LABEL, MODE_LABEL } from '../types'
import type { ContentTask, TaskStatus } from '../types'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'

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
]

export function TaskList({ selectedTaskId, onSelectTask }: TaskListProps) {
  const { data: tasks, isLoading, refetch, isFetching } = useTaskList()
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* 搜索和筛选 */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="搜索任务..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-7 pl-7 text-xs"
          />
        </div>
        <div className="flex gap-1 flex-wrap">
          {FILTER_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={statusFilter === opt.value ? 'default' : 'ghost'}
              size="sm"
              className="h-6 px-2 text-[10px]"
              onClick={() => setStatusFilter(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching} className="h-6 px-2">
            <RefreshCw className={cn('w-3 h-3', isFetching && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {filteredTasks.length === 0 ? (
        <div className="text-center py-8 text-sm text-muted-foreground">
          {tasks && tasks.length > 0 ? '没有匹配的任务' : '暂无任务记录'}
        </div>
      ) : (
        <ScrollArea className="h-[calc(100vh-420px)]">
          <motion.div
            className="space-y-2 pr-3"
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
                />
              </motion.div>
            ))}
          </motion.div>
        </ScrollArea>
      )}
    </div>
  )
}

function TaskCard({ task, isSelected, onClick }: {
  task: ContentTask
  isSelected: boolean
  onClick: () => void
}) {
  const Icon = STATUS_ICON[task.status]
  const isActive = ['pending', 'queued', 'running'].includes(task.status)

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:border-primary/30',
        isSelected && 'border-primary/50 bg-primary/5',
      )}
      onClick={onClick}
    >
      <CardContent className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {task.mode === 'search' ? (
              <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            )}
            <span className="text-sm font-medium truncate">
              {task.source_title || task.keyword || (task.mode === 'direct' ? `直投内容 #${task.id}` : `任务 #${task.id}`)}
            </span>
          </div>
          <Badge variant={STATUS_VARIANT[task.status]} className="shrink-0 text-[10px] px-1.5 py-0">
            <Icon className={cn('w-3 h-3 mr-0.5', isActive && 'animate-spin')} />
            {STATUS_LABEL[task.status]}
          </Badge>
        </div>

        {isActive && (
          <div className="space-y-1">
            <Progress value={task.progress} className="h-1" />
            <p className="text-[10px] text-muted-foreground">{task.message || '处理中...'}</p>
          </div>
        )}

        {task.status === 'failed' && task.error && (
          <p className="text-[10px] text-destructive line-clamp-2">{task.error}</p>
        )}

        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>{MODE_LABEL[task.mode]}</span>
          <span>·</span>
          <span>{formatDistanceToNow(new Date(task.created_at), { addSuffix: true, locale: zhCN })}</span>
        </div>
      </CardContent>
    </Card>
  )
}
