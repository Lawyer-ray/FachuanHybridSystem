import { useNavigate } from 'react-router'
import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Eye, Paperclip, FileText, Image, File, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS } from '@/routes/paths'
import { getAccessToken } from '@/lib/token'
import { inboxApi } from '../api'
import { formatDate } from '@/lib/date'
import type { InboxMessageDetail, AttachmentMeta } from '../types'

const SOURCE_LABELS: Record<string, string> = {
  imap: 'IMAP 邮箱',
  court_inbox: '一张网收件箱',
  court_schedule: '一张网庭审日程',
}

const SOURCE_COLORS: Record<string, string> = {
  imap: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  court_inbox: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
  court_schedule: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function canPreview(contentType: string): boolean {
  return contentType.includes('pdf') || contentType.startsWith('image/')
}

function getFileIcon(contentType: string) {
  if (contentType.includes('pdf')) return FileText
  if (contentType.startsWith('image/')) return Image
  return File
}

function openAttachment(messageId: number, att: AttachmentMeta, inline: boolean) {
  const url = inline
    ? inboxApi.attachmentPreviewUrl(messageId, att.part_index)
    : inboxApi.attachmentDownloadUrl(messageId, att.part_index)
  const token = getAccessToken()
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then((res) => {
      if (!res.ok) throw new Error('下载失败')
      return res.blob()
    })
    .then((blob) => {
      const blobUrl = URL.createObjectURL(blob)
      if (inline) {
        window.open(blobUrl, '_blank')
      } else {
        const a = document.createElement('a')
        a.href = blobUrl
        a.download = att.filename
        a.click()
        URL.revokeObjectURL(blobUrl)
      }
    })
    .catch(() => {})
}

function getEffectiveFilename(att: AttachmentMeta): string {
  if (att.custom_filename) return att.custom_filename
  if (att.original_filename) return att.original_filename
  return att.filename
}

interface AttachmentCardProps {
  att: AttachmentMeta
  messageId: number
  onRenamed: () => void
}

function AttachmentCard({ att, messageId, onRenamed }: AttachmentCardProps) {
  const [editValue, setEditValue] = useState(() => getEffectiveFilename(att))
  const [saving, setSaving] = useState(false)
  const original = att.original_filename || att.filename
  const effective = getEffectiveFilename(att)
  const isDirty = editValue !== effective

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await inboxApi.renameAttachment(messageId, att.part_index, editValue)
      toast.success('附件已重命名')
      onRenamed()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '重命名失败')
    } finally {
      setSaving(false)
    }
  }, [messageId, att.part_index, editValue, onRenamed])

  const handleReset = useCallback(() => {
    setEditValue(original)
  }, [original])

  const Icon = getFileIcon(att.content_type)

  return (
    <div className="p-3.5 rounded-xl border border-border bg-gradient-to-b from-white to-slate-50/50 dark:from-slate-900 dark:to-slate-950/50 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="shrink-0 p-2 rounded-lg bg-muted">
            <Icon className="size-5 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{original}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-muted text-[11px] text-muted-foreground">
                {formatSize(att.size)}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {att.content_type || '未知类型'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 重命名编辑器 */}
      <div className="mt-3 flex items-center gap-2">
        <Input
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          placeholder="下载文件名"
          className="h-9 flex-1"
          disabled={saving}
        />
        {isDirty && (
          <Button variant="ghost" size="sm" className="h-9 px-2.5" onClick={handleReset} disabled={saving} title="恢复原名">
            <RotateCcw className="size-3.5" />
          </Button>
        )}
        <Button size="sm" className="h-9 px-3" onClick={handleSave} disabled={saving || !isDirty}>
          {saving ? '...' : '保存'}
        </Button>
        <div className="h-5 w-px bg-border mx-0.5" />
        {canPreview(att.content_type) && (
          <Button variant="outline" size="sm" className="h-9 px-2.5" onClick={() => openAttachment(messageId, att, true)}>
            <Eye className="size-3.5" />
          </Button>
        )}
        <Button variant="outline" size="sm" className="h-9 px-2.5" onClick={() => openAttachment(messageId, att, false)}>
          <Download className="size-3.5" />
        </Button>
      </div>
      {att.custom_filename && (
        <p className="text-[11px] text-muted-foreground mt-1.5">
          原始文件名：{original}
        </p>
      )}
    </div>
  )
}

interface Props {
  message: InboxMessageDetail
}

export function InboxMessageView({ message }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const handleRenamed = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['inbox-message', message.id] })
  }, [queryClient, message.id])

  return (
    <div className="space-y-4">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between">
        <Button
          variant="ghost" size="sm"
          onClick={() => navigate(PATHS.ADMIN_INBOX)}
          className="gap-1.5 text-muted-foreground"
        >
          <ArrowLeft className="size-4" />
          返回列表
        </Button>
      </div>

      {/* 主题标题 */}
      <div>
        <h1 className="text-xl font-semibold leading-snug">
          {message.subject || '(无主题)'}
        </h1>
        <div className="flex items-center gap-2 mt-1.5">
          <Badge variant="outline" className={`text-[11px] font-medium ${SOURCE_COLORS[message.source_type] ?? ''}`}>
            {SOURCE_LABELS[message.source_type] || message.source_type}
          </Badge>
          {message.attachments.length > 0 && (
            <Badge variant="secondary" className="text-[11px]">
              {message.attachments.length} 个附件
            </Badge>
          )}
        </div>
      </div>

      {/* Section 1: 基本信息 */}
      <Card className="py-4">
        <CardContent className="px-4">
          <div className="text-xs font-medium text-muted-foreground mb-3">基本信息</div>
          <div className="grid gap-y-2.5 gap-x-8 text-sm sm:grid-cols-2">
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">发件人</span>
              <span className="font-medium">{message.sender || '-'}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">收件人</span>
              <span>{message.recipient}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">来源</span>
              <span>{message.source_name}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">接收时间</span>
              <span>{formatDate(message.received_at)}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">原始 ID</span>
              <span className="font-mono text-xs text-muted-foreground truncate">{message.message_id}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted-foreground w-14 shrink-0 text-right">入库时间</span>
              <span>{formatDate(message.created_at)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 2: 正文 */}
      <Card className="py-4">
        <CardContent className="px-4">
          <div className="text-xs font-medium text-muted-foreground mb-3">正文</div>
          {message.body_html ? (
            <iframe
              srcDoc={message.body_html}
              sandbox=""
              className="w-full bg-white rounded-md border border-border"
              style={{ height: 'min(60vh, 750px)' }}
            />
          ) : message.body_text ? (
            <div className="whitespace-pre-wrap text-sm leading-relaxed p-4 bg-muted/30 rounded-md border border-border overflow-auto max-h-[min(60vh,750px)]">
              {message.body_text}
            </div>
          ) : (
            <div className="text-muted-foreground text-sm text-center py-16 border border-dashed border-border rounded-md">
              无正文内容
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 3: 附件 */}
      <Card className="py-4">
        <CardContent className="px-4">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-3">
            <Paperclip className="size-3.5" />
            附件 ({message.attachments.length})
          </div>
          <p className="text-[12px] text-muted-foreground mb-3">
            可直接调整附件下载名；留空则使用原始文件名。
          </p>
          {message.attachments.length > 0 ? (
            <div className="flex flex-col gap-3">
              {message.attachments.map((att) => (
                <AttachmentCard
                  key={att.part_index}
                  att={att}
                  messageId={message.id}
                  onRenamed={handleRenamed}
                />
              ))}
            </div>
          ) : (
            <div className="text-muted-foreground text-sm text-center py-8 border border-dashed border-border rounded-md">
              无附件
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/** 详情页加载骨架 */
export function InboxMessageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-20" />
      <div>
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-5 w-24 mt-2" />
      </div>
      <Card className="py-4">
        <CardContent className="px-4">
          <Skeleton className="h-4 w-16 mb-3" />
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex gap-2">
                <Skeleton className="h-4 w-14" />
                <Skeleton className="h-4 flex-1" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="py-4">
        <CardContent className="px-4">
          <Skeleton className="h-4 w-10 mb-3" />
          <Skeleton className="h-[500px] w-full" />
        </CardContent>
      </Card>
    </div>
  )
}
