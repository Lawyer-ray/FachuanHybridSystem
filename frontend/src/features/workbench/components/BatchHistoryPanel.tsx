/* eslint-disable react-refresh/only-export-components */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, Download, ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { listBatchJobs } from '../api'
import type { BatchJob } from '../types'

interface BatchHistoryPanelProps {
  sessionId: number
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === 'completed' ? 'secondary' : status === 'running' ? 'default' : 'destructive'
  const label = status === 'completed' ? '已完成' : status === 'running' ? '运行中' : status === 'failed' ? '失败' : status === 'cancelled' ? '已取消' : status
  return <Badge variant={variant} className="text-[10px] px-1.5 py-0">{label}</Badge>
}

function BatchJobRow({ job }: { job: BatchJob }) {
  const [expanded, setExpanded] = useState(false)

  const handleDownload = () => {
    if (!job.summary_file) return
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
    const token = localStorage.getItem('access_token')
    window.open(`${baseUrl}/workbench/batch/${job.id}/download${token ? `?token=${token}` : ''}`, '_blank')
  }

  return (
    <div className="border rounded-md">
      <div className="flex items-center gap-2 px-3 py-2 text-xs">
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          {job.status === 'running' && <Loader2 className="size-3 animate-spin text-blue-600 shrink-0" />}
          {job.status === 'completed' && <CheckCircle2 className="size-3 text-green-600 shrink-0" />}
          {(job.status === 'failed' || job.status === 'cancelled') && <XCircle className="size-3 text-red-600 shrink-0" />}
          <StatusBadge status={job.status} />
          <span className="text-muted-foreground truncate">{job.total_items} 个文件</span>
        </div>
        <span className="text-muted-foreground shrink-0">{formatDate(job.created_at)}</span>
        {job.summary_file && (
          <button
            onClick={(e) => { e.stopPropagation(); handleDownload() }}
            className="shrink-0 text-muted-foreground hover:text-foreground"
            title="下载 CSV"
          >
            <Download className="size-3" />
          </button>
        )}
      </div>

      {/* 详细信息 */}
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger asChild>
          <button className="flex w-full items-center justify-between px-3 py-1 text-[10px] text-muted-foreground hover:bg-muted/50">
            <span>详情</span>
            {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-2 space-y-1 text-[11px]">
            <div className="text-muted-foreground truncate">分析要求：{job.prompt}</div>
            <div className="flex gap-3">
              <span className="text-green-600">成功 {job.completed_items}</span>
              <span className="text-red-600">失败 {job.failed_items}</span>
              {job.started_at && (
                <span className="text-muted-foreground flex items-center gap-0.5">
                  <Clock className="size-2.5" />
                  {formatDate(job.started_at)}
                  {job.finished_at && ` → ${formatDate(job.finished_at)}`}
                </span>
              )}
            </div>
            {job.error_message && (
              <div className="text-destructive truncate">{job.error_message}</div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

export function BatchHistoryPanel({ sessionId }: BatchHistoryPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['batch-jobs', sessionId],
    queryFn: () => listBatchJobs(sessionId),
    enabled: !!sessionId,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const jobs = data?.items ?? []

  if (jobs.length === 0) {
    return (
      <div className="text-center py-4 text-xs text-muted-foreground">
        <History className="size-6 mx-auto mb-1 opacity-50" />
        <p>暂无批量分析历史</p>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {jobs.map((job) => (
        <BatchJobRow key={job.id} job={job} />
      ))}
    </div>
  )
}
