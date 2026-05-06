/* eslint-disable react-refresh/only-export-components */
import { useState } from 'react'
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { BatchJob, BatchJobItem } from '../types'

interface BatchProgressCardProps {
  job: BatchJob
  items: BatchJobItem[]
  onCancel: () => void
}

export function BatchProgressCard({ job, items, onCancel }: BatchProgressCardProps) {
  const [expanded, setExpanded] = useState(false)

  const isRunning = job.status === 'running' || job.status === 'pending'
  const isCompleted = job.status === 'completed'
  const isFailed = job.status === 'failed'
  const isCancelled = job.status === 'cancelled'

  const statusColor = isRunning
    ? 'text-blue-600'
    : isCompleted
      ? 'text-green-600'
      : isFailed
        ? 'text-red-600'
        : 'text-muted-foreground'

  const statusText = isRunning
    ? '分析中'
    : isCompleted
      ? '已完成'
      : isFailed
        ? '失败'
        : isCancelled
          ? '已取消'
          : job.status

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 className="size-4 animate-spin text-blue-600" />}
          {isCompleted && <CheckCircle2 className="size-4 text-green-600" />}
          {(isFailed || isCancelled) && <XCircle className="size-4 text-red-600" />}
          <span className="font-medium text-sm">批量文档分析</span>
          <Badge variant={isRunning ? 'default' : isCompleted ? 'secondary' : 'destructive'}>
            {statusText}
          </Badge>
        </div>
        {isRunning && (
          <Button variant="ghost" size="sm" onClick={onCancel} className="h-7 text-xs">
            <X className="size-3 mr-1" />
            取消
          </Button>
        )}
      </div>

      {/* 进度条 */}
      <div className="space-y-1">
        <Progress value={job.progress} className="h-2" />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{job.completed_items + job.failed_items} / {job.total_items}</span>
          <span className={statusColor}>{job.progress}%</span>
        </div>
      </div>

      {/* 统计 */}
      <div className="flex gap-3 text-xs">
        <span className="text-green-600">成功: {job.completed_items}</span>
        <span className="text-red-600">失败: {job.failed_items}</span>
        <span className="text-muted-foreground">待处理: {job.total_items - job.completed_items - job.failed_items}</span>
      </div>

      {/* 汇总结果 */}
      {isCompleted && job.summary && (
        <div className="rounded-md bg-muted p-3 text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
          {job.summary}
        </div>
      )}

      {/* 错误信息 */}
      {(isFailed || isCancelled) && job.error_message && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {job.error_message}
        </div>
      )}

      {/* 可展开的文件列表 */}
      {items.length > 0 && (
        <Collapsible open={expanded} onOpenChange={setExpanded}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full justify-between h-7 text-xs">
              <span>查看文件详情 ({items.length})</span>
              {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="max-h-60 overflow-y-auto space-y-1 mt-2">
              {items.map((item) => (
                <div key={item.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-muted/50">
                  {item.status === 'running' && <Loader2 className="size-3 animate-spin text-blue-600 shrink-0" />}
                  {item.status === 'completed' && <CheckCircle2 className="size-3 text-green-600 shrink-0" />}
                  {item.status === 'failed' && <XCircle className="size-3 text-red-600 shrink-0" />}
                  {item.status === 'pending' && <span className="size-3 rounded-full border border-muted-foreground shrink-0" />}
                  <span className="truncate flex-1">{item.file_name}</span>
                  {item.duration_ms != null && (
                    <span className="text-muted-foreground shrink-0">
                      {(item.duration_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
