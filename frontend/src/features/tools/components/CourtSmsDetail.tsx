import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Trash2, FileWarning, Link2, AlertTriangle,
  CheckCircle2, XCircle, Clock, Download, Pencil, FolderDown,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'
import { formatDate } from '@/lib/date'

import { getAccessToken } from '@/lib/token'

import { useCourtSms } from '../hooks/use-court-sms'
import { courtSmsApi } from '../api/court-sms'
import { DetailField, DetailCard, StatusBadge } from '@/components/shared'

export interface CourtSmsDetailProps { smsId: number }

/* ── Constants ── */

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理', parsing: '解析中', downloading: '下载中',
  download_failed: '下载失败', matching: '匹配中', pending_manual: '待人工处理',
  renaming: '重命名中', notifying: '通知中', completed: '已完成', failed: '处理失败',
}

const SMS_TYPE_LABELS: Record<string, string> = {
  document_delivery: '文书送达', info_notification: '信息通知', filing_notification: '立案通知',
}

const RECOMMENDATION_REASON_LABELS: Record<string, string> = {
  court_sms_acceptance_match: '受理通知书规则命中',
  court_sms_fee_invoice_match: '缴费/发票规则命中',
  court_sms_opponent_material_match: '对方材料强规则命中',
  court_sms_opponent_material_weak_match: '对方材料弱规则命中',
  court_sms_judgment_notice_match: '裁定/判决/通知规则命中',
  court_sms_other_fallback: '法院送达材料默认兜底',
}

function CourtSmsStatusBadge({ status }: { status: string | null }) {
  if (!status) return <StatusBadge variant="closed">未设置</StatusBadge>
  const variant = status === 'completed'
    ? 'active'
    : status === 'failed' || status === 'download_failed'
      ? 'error'
      : status === 'pending_manual'
        ? 'warning'
        : 'info'
  return <StatusBadge variant={variant}>{STATUS_LABELS[status] ?? status}</StatusBadge>
}

/* ── Notification results ── */

function NotificationResults({ results }: { results: Record<string, unknown> | null }) {
  if (!results || Object.keys(results).length === 0) {
    return <span className="text-muted-foreground text-xs">无通知记录</span>
  }
  return (
    <div className="space-y-2">
      {Object.entries(results).map(([platform, result]) => {
        const r = result as Record<string, unknown>
        const success = Boolean(r.success ?? r.status === 'sent')
        const sentAt = (r.sent_at ?? r.timestamp) as string | undefined
        const error = (r.error ?? r.error_message) as string | undefined
        return (
          <div key={platform} className="flex items-start gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px]">
            {success ? (
              <CheckCircle2 className="size-4 text-green-500 mt-0.5 shrink-0" />
            ) : error ? (
              <XCircle className="size-4 text-red-500 mt-0.5 shrink-0" />
            ) : (
              <Clock className="size-4 text-muted-foreground mt-0.5 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <div className="font-medium text-xs">{platform}</div>
              {sentAt && <div className="text-muted-foreground text-xs">时间: {formatDate(sentAt)}</div>}
              {error && <div className="text-destructive text-xs mt-0.5">{error}</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Main component ── */

export function CourtSmsDetail({ smsId }: CourtSmsDetailProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: sms, isLoading, error } = useCourtSms(smsId)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [renamingIndex, setRenamingIndex] = useState<number | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const handleBack = useCallback(() => navigate(PATHS.ADMIN_TOOLS_COURT_SMS), [navigate])

  const handleDelete = useCallback(async () => {
    try {
      await courtSmsApi.delete(smsId)
      toast.success('短信已删除')
      queryClient.invalidateQueries({ queryKey: ['court-sms'] })
      navigate(PATHS.ADMIN_TOOLS_COURT_SMS)
    } catch {
      toast.error('删除失败')
    }
  }, [smsId, navigate, queryClient])

  const handleDownload = useCallback(async (refIndex: number) => {
    try {
      const url = courtSmsApi.downloadDocumentUrl(smsId, refIndex)
      const token = getAccessToken()
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!res.ok) throw new Error(`下载失败 (${res.status})`)
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = sms?.documents[refIndex]?.name || 'document'
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '下载失败')
    }
  }, [smsId, sms])

  const handleDownloadAll = useCallback(async () => {
    try {
      const url = courtSmsApi.downloadAllUrl(smsId)
      const token = getAccessToken()
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!res.ok) throw new Error(`下载失败 (${res.status})`)
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `courtsms_${smsId}_documents.zip`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '批量下载失败')
    }
  }, [smsId])

  const handleRename = useCallback(async (refIndex: number) => {
    if (!renameValue.trim()) return
    try {
      const result = await courtSmsApi.renameDocument(smsId, refIndex, renameValue.trim())
      if (result.success) {
        toast.success('重命名成功')
        setRenamingIndex(null)
        setRenameValue('')
        queryClient.invalidateQueries({ queryKey: ['court-sms', smsId] })
      } else {
        toast.error(result.error || '重命名失败')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重命名失败')
    }
  }, [smsId, renameValue, queryClient])

  if (isLoading) return <DetailSkeleton />

  if (error || !sms) return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
      <h2 className="mb-2 text-xl font-semibold">短信不存在</h2>
      <p className="text-muted-foreground mb-6">您访问的短信记录可能已被删除或不存在</p>
      <Button onClick={handleBack} variant="outline"><ArrowLeft className="mr-2 size-4" />返回列表</Button>
    </div>
  )

  const typeLabel = sms.sms_type ? (SMS_TYPE_LABELS[sms.sms_type] ?? sms.sms_type) : null

  return (
    <div className="space-y-0">
      {/* ── Page Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-3 mb-5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-semibold">短信 #{sms.id}</h1>
            <CourtSmsStatusBadge status={sms.status} />
            {typeLabel && <Badge variant="outline" className="text-[11px] px-2 py-0.5">{typeLabel}</Badge>}
          </div>
          <div className="mt-1.5 text-[13px] text-muted-foreground">
            收到时间：{formatDate(sms.received_at)}
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleBack}>
            <ArrowLeft className="mr-1 size-3.5" />返回列表
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="mr-1 size-3.5" />删除
          </Button>
        </div>
      </div>

      {/* ── 短信内容 ── */}
      <DetailCard title="短信内容">
        <div className="rounded-md bg-muted/50 p-4 text-[13px] whitespace-pre-wrap">{sms.content}</div>
      </DetailCard>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── 基本信息 ── */}
        <DetailCard title="基本信息">
          <div className="grid gap-[14px] sm:grid-cols-2">
            <DetailField label="短信ID" value={sms.id} mono />
            <DetailField label="状态" value={<CourtSmsStatusBadge status={sms.status} />} />
            <DetailField label="短信类型" value={typeLabel} />
            <DetailField label="收到时间" value={formatDate(sms.received_at)} mono />
            <DetailField label="创建时间" value={formatDate(sms.created_at)} mono />
            <DetailField label="更新时间" value={formatDate(sms.updated_at)} mono />
            {sms.retry_count > 0 && <DetailField label="重试次数" value={sms.retry_count} />}
          </div>
        </DetailCard>

        {/* ── 关联案件 ── */}
        <DetailCard title="关联信息">
          <div className="grid gap-[14px]">
            <DetailField
              label="关联案件"
              value={sms.case ? (
                <a href={generatePath.caseDetail(String(sms.case.id))} className="text-primary hover:underline font-medium">
                  {sms.case.name}
                </a>
              ) : '—'}
            />
            {sms.case_numbers.length > 0 && (
              <div>
                <div className="text-muted-foreground mb-1 text-xs">案号</div>
                <div className="flex flex-wrap gap-1.5">
                  {sms.case_numbers.map((cn, i) => (
                    <Badge key={i} variant="secondary" className="text-[11px] px-2 py-0.5">{cn}</Badge>
                  ))}
                </div>
              </div>
            )}
            {sms.party_names.length > 0 && (
              <div>
                <div className="text-muted-foreground mb-1 text-xs">当事人</div>
                <div className="flex flex-wrap gap-1.5">
                  {sms.party_names.map((pn, i) => (
                    <Badge key={i} variant="outline" className="text-[11px] px-2 py-0.5">{pn}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DetailCard>
      </div>

      {/* ── 文书 ── */}
      {sms.documents.length > 0 && (
        <DetailCard title="关联文书" extra={
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleDownloadAll}>
            <FolderDown className="mr-1 size-3.5" />全部下载
          </Button>
        }>
          <div className="flex flex-col gap-2">
            {sms.documents.map((doc, idx) => (
              <div key={`${doc.id ?? 'doc'}-${idx}-${doc.name}`} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px]">
                <Link2 className="text-muted-foreground size-3.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  {renamingIndex === idx ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleRename(idx); if (e.key === 'Escape') setRenamingIndex(null) }}
                        className="flex-1 rounded border border-input bg-background px-2 py-1 text-xs"
                        autoFocus
                      />
                      <Button size="sm" className="h-6 px-2 text-xs" onClick={() => handleRename(idx)}>确定</Button>
                      <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setRenamingIndex(null)}>取消</Button>
                    </div>
                  ) : (
                    <>
                      <span className="font-medium truncate block">{doc.name}</span>
                      {doc.source && <span className="text-muted-foreground text-xs">{doc.source}</span>}
                      <div className="mt-1.5 space-y-1 text-xs">
                        {doc.original_name && (
                          <div className="text-muted-foreground">
                            原始文书名: <span className="font-medium text-foreground">{doc.original_name}</span>
                          </div>
                        )}
                        <div className="text-muted-foreground">
                          当前归档子目录: <span className="font-medium text-foreground">{doc.archived_subdir || '未归档/未记录'}</span>
                        </div>
                        <div className="text-muted-foreground">
                          系统推荐子目录: <span className="font-medium text-foreground">{doc.recommended_subdir || '未给出'}</span>
                        </div>
                        {doc.recommendation_reason && (
                          <div className="text-muted-foreground">
                            推荐依据:{' '}
                            <span className="font-medium text-foreground">
                              {RECOMMENDATION_REASON_LABELS[doc.recommendation_reason] ?? doc.recommendation_reason}
                            </span>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
                {renamingIndex !== idx && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => { setRenamingIndex(idx); setRenameValue(doc.name.replace(/\.[^.]+$/, '')) }}>
                      <Pencil className="mr-1 size-3" />重命名
                    </Button>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => handleDownload(idx)}>
                      <Download className="mr-1 size-3" />下载
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </DetailCard>
      )}

      {/* ── 下载链接 ── */}
      {sms.download_links.length > 0 && (
        <DetailCard title="下载链接">
          <div className="flex flex-col gap-1.5">
            {sms.download_links.map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline truncate">
                {url}
              </a>
            ))}
          </div>
        </DetailCard>
      )}

      {/* ── 错误信息 ── */}
      {sms.error_message && (
        <DetailCard title="错误信息" extra={<AlertTriangle className="text-destructive size-4" />}>
          <div className="rounded-md bg-destructive/10 p-3 text-xs text-destructive">{sms.error_message}</div>
        </DetailCard>
      )}

      {/* ── 通知状态 ── */}
      {(sms.notification_results || sms.feishu_sent_at) && (
        <DetailCard title="通知状态">
          {sms.notification_results ? (
            <NotificationResults results={sms.notification_results} />
          ) : (
            <div className="flex items-center gap-2 text-[13px]">
              {sms.feishu_sent_at ? (
                <>
                  <CheckCircle2 className="size-4 text-green-500" />
                  <span>飞书已通知 {formatDate(sms.feishu_sent_at)}</span>
                </>
              ) : sms.feishu_error ? (
                <>
                  <XCircle className="size-4 text-red-500" />
                  <span className="text-destructive">飞书通知失败: {sms.feishu_error}</span>
                </>
              ) : (
                <span className="text-muted-foreground text-xs">未通知</span>
              )}
            </div>
          )}
        </DetailCard>
      )}

      {/* ── Delete Dialog ── */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除短信</AlertDialogTitle>
            <AlertDialogDescription>删除短信 #{sms.id} 后无法恢复。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">确认删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/* ── Skeleton ── */

function DetailSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="bg-muted h-6 w-56 animate-pulse rounded" />
          <div className="bg-muted h-4 w-40 animate-pulse rounded" />
        </div>
        <div className="flex gap-2">
          <div className="bg-muted h-8 w-20 animate-pulse rounded-md" />
          <div className="bg-muted h-8 w-20 animate-pulse rounded-md" />
        </div>
      </div>
      <div className="bg-muted h-64 w-full animate-pulse rounded-lg" />
    </div>
  )
}

export default CourtSmsDetail
