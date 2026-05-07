/* eslint-disable react-refresh/only-export-components */
import { useState } from 'react'
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp, X, RefreshCw, Clock, Gauge } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { toast } from 'sonner'
import * as batchApi from '../api'
import type { BatchJob, BatchJobItem, FailedItemDetail } from '../types'

interface BatchProgressCardProps {
  job: BatchJob
  items: BatchJobItem[]
  onCancel: () => void
  failedItemsDetail?: FailedItemDetail[]
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return `${h}小时${m}分钟`
}

export function BatchProgressCard({ job, items, onCancel, failedItemsDetail = [] }: BatchProgressCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const isRunning = job.status === 'running' || job.status === 'pending'
  const isCompleted = job.status === 'completed'
  const isFailed = job.status === 'failed'
  const isCancelled = job.status === 'cancelled'
  const isTerminal = isCompleted || isFailed || isCancelled

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

  const handleRetry = async () => {
    setRetrying(true)
    try {
      const result = await batchApi.retryBatchAnalysis(job.id)
      if (result.success) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch {
      toast.error('重试请求失败')
    } finally {
      setRetrying(false)
    }
  }

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
        <div className="flex items-center gap-1">
          {isTerminal && job.failed_items > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRetry}
              disabled={retrying}
              className="h-7 text-xs"
            >
              <RefreshCw className={`size-3 mr-1 ${retrying ? 'animate-spin' : ''}`} />
              重试失败项
            </Button>
          )}
          {isRunning && (
            <Button variant="ghost" size="sm" onClick={onCancel} className="h-7 text-xs">
              <X className="size-3 mr-1" />
              取消
            </Button>
          )}
        </div>
      </div>

      {/* 进度条 */}
      <div className="space-y-1">
        <Progress value={job.progress} className="h-2" />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{job.completed_items + job.failed_items} / {job.total_items}</span>
          <span className={statusColor}>{job.progress}%</span>
        </div>
      </div>

      {/* 统计 + 速度/ETA */}
      <div className="flex flex-wrap gap-3 text-xs">
        <span className="text-green-600">成功: {job.completed_items}</span>
        <span className="text-red-600">失败: {job.failed_items}</span>
        <span className="text-muted-foreground">待处理: {job.total_items - job.completed_items - job.failed_items}</span>
        {isRunning && job.speed_per_minute > 0 && (
          <span className="text-muted-foreground flex items-center gap-1">
            <Gauge className="size-3" />
            {job.speed_per_minute.toFixed(1)} 文件/分钟
          </span>
        )}
        {isRunning && job.eta_seconds != null && job.eta_seconds > 0 && (
          <span className="text-muted-foreground flex items-center gap-1">
            <Clock className="size-3" />
            预计剩余: {formatDuration(job.eta_seconds)}
          </span>
        )}
      </div>

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

              {/* 失败文件详情 */}
              {failedItemsDetail.length > 0 && (
                <div className="mt-2 pt-2 border-t">
                  <div className="text-xs font-medium text-destructive mb-1">失败详情</div>
                  {failedItemsDetail.map((item) => (
                    <div key={item.id} className="text-xs py-1 px-2 text-destructive/80">
                      <span className="font-medium">{item.file_name}</span>
                      {item.error && <span className="ml-2">— {item.error}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
