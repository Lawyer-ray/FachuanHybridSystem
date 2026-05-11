/* eslint-disable react-refresh/only-export-components */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, Download, ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react'

import { StatusBadge } from '@/components/shared'
import { Button } from '@/components/ui/button'
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogFooter, AlertDialogCancel,
} from '@/components/ui/alert-dialog'
import { API_BASE_URL } from '@/lib/api'
import { getAccessToken } from '@/lib/token'
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

function BatchStatusBadge({ status }: { status: string }) {
  const variant = status === 'completed'
    ? 'closed'
    : status === 'running'
      ? 'info'
      : status === 'failed'
        ? 'error'
        : 'closed'
  const label = status === 'completed' ? '已完成' : status === 'running' ? '运行中' : status === 'failed' ? '失败' : status === 'cancelled' ? '已取消' : status
  return <StatusBadge variant={variant}>{label}</StatusBadge>
}

type DownloadType = 'csv' | 'zip' | null

function BatchJobRow({ job }: { job: BatchJob }) {
  const [expanded, setExpanded] = useState(false)
  const [downloadType, setDownloadType] = useState<DownloadType>(null)

  const doDownload = (type: 'csv' | 'zip', relevantOnly: boolean) => {
    const baseUrl = API_BASE_URL
    const token = getAccessToken()
    const endpoint = type === 'csv' ? 'download' : 'download-detail'
    const params = new URLSearchParams()
    if (token) params.set('token', token)
    if (relevantOnly) params.set('relevant_only', 'true')
    window.open(`${baseUrl}/workbench/batch/${job.id}/${endpoint}?${params.toString()}`, '_blank')
    setDownloadType(null)
  }

  return (
    <>
      <div className="border rounded-md">
        <div className="flex items-center gap-2 px-3 py-2 text-xs">
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            {job.status === 'running' && <Loader2 className="size-3 animate-spin text-blue-600 shrink-0" />}
            {job.status === 'completed' && <CheckCircle2 className="size-3 text-green-600 shrink-0" />}
            {(job.status === 'failed' || job.status === 'cancelled') && <XCircle className="size-3 text-red-600 shrink-0" />}
            <BatchStatusBadge status={job.status} />
            <span className="text-muted-foreground truncate">{job.total_items} 个文件</span>
          </div>
          <span className="text-muted-foreground shrink-0">{formatDate(job.created_at)}</span>
          {job.summary_file && (
            <Button variant="outline" size="xs" onClick={() => setDownloadType('csv')}>
              <Download className="size-3" />
              CSV
            </Button>
          )}
          {job.detail_zip_file && (
            <Button variant="outline" size="xs" onClick={() => setDownloadType('zip')}>
              <Download className="size-3" />
              ZIP
            </Button>
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

      <AlertDialog open={downloadType !== null} onOpenChange={(open) => { if (!open) setDownloadType(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              下载{downloadType === 'csv' ? '汇总 CSV' : '分析详情 ZIP'}
            </AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-sm text-muted-foreground">
            选择下载范围：仅下载与研究问题相关的案例，或下载全部案例。
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button variant="outline" onClick={() => doDownload(downloadType!, true)}>
              仅相关案例
            </Button>
            <Button onClick={() => doDownload(downloadType!, false)}>
              全部案例
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
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
