import { useNavigate } from 'react-router'
import { ArrowLeft, Download, Eye, Paperclip, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function canPreview(contentType: string): boolean {
  return contentType.includes('pdf') || contentType.startsWith('image/')
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

interface Props {
  message: InboxMessageDetail
}

export function InboxMessageView({ message }: Props) {
  const navigate = useNavigate()
  const [showDetails, setShowDetails] = useState(false)

  return (
    <div className="space-y-3">
      {/* 顶部：返回 + 标题 */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost" size="sm"
          onClick={() => navigate(PATHS.ADMIN_INBOX)}
          className="shrink-0 gap-1"
        >
          <ArrowLeft className="size-4" />
          返回
        </Button>
        <h1 className="text-lg font-semibold leading-snug truncate">
          {message.subject || '(无主题)'}
        </h1>
      </div>

      {/* 元信息卡片 */}
      <Card className="py-3">
        <CardContent className="px-4">
          <div className="grid gap-y-2 gap-x-6 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground w-14 shrink-0">发件人</span>
              <span className="font-medium truncate">{message.sender || '-'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground w-14 shrink-0">收件人</span>
              <span className="truncate">{message.recipient}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground w-14 shrink-0">时间</span>
              <span>{formatDate(message.received_at)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground w-14 shrink-0">来源</span>
              <Badge variant="outline" className="text-[11px] font-normal">
                {SOURCE_LABELS[message.source_type] || message.source_type}
              </Badge>
              <span className="text-muted-foreground text-[12px]">{message.source_name}</span>
            </div>
            {message.attachments.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground w-14 shrink-0">附件</span>
                <Badge variant="secondary" className="text-[11px]">
                  {message.attachments.length} 个
                </Badge>
              </div>
            )}
          </div>

          {/* 可展开的详细信息 */}
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 mt-2 text-[12px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronDown className={`size-3.5 transition-transform ${showDetails ? 'rotate-180' : ''}`} />
            {showDetails ? '收起详情' : '展开详情'}
          </button>
          {showDetails && (
            <div className="mt-2 pt-2 border-t border-border grid gap-y-1.5 gap-x-6 text-[12px] sm:grid-cols-2">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground w-14 shrink-0">原始 ID</span>
                <span className="font-mono truncate">{message.message_id}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground w-14 shrink-0">入库时间</span>
                <span>{formatDate(message.created_at)}</span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 邮件正文 */}
      <Card className="py-3">
        <CardContent className="px-4">
          <div className="text-xs font-medium text-muted-foreground mb-2">邮件正文</div>
          {message.body_html ? (
            <iframe
              srcDoc={message.body_html}
              sandbox=""
              className="w-full bg-white rounded-md border border-border min-h-[400px] h-auto"
              onLoad={(e) => {
                const iframe = e.currentTarget
                const doc = iframe.contentDocument
                if (doc?.body) {
                  iframe.style.height = `${doc.body.scrollHeight + 24}px`
                }
              }}
            />
          ) : message.body_text ? (
            <div className="whitespace-pre-wrap text-sm leading-relaxed p-4 bg-muted/30 rounded-md border border-border max-h-[600px] overflow-y-auto">
              {message.body_text}
            </div>
          ) : (
            <div className="text-muted-foreground text-sm text-center py-12">
              无正文内容
            </div>
          )}
        </CardContent>
      </Card>

      {/* 附件 */}
      {message.attachments.length > 0 && (
        <Card className="py-3">
          <CardContent className="px-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Paperclip className="size-3.5" />
                附件 ({message.attachments.length})
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              {message.attachments.map((att) => (
                <div
                  key={att.part_index}
                  className="flex items-center gap-3 px-3 py-2 rounded-md border border-border hover:bg-muted/30 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] truncate">{att.filename}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {formatSize(att.size)} · {att.content_type || '未知类型'}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {canPreview(att.content_type) && (
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => openAttachment(message.id, att, true)}
                        className="h-7 px-2 text-[11px]"
                      >
                        <Eye className="size-3" />
                      </Button>
                    )}
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => openAttachment(message.id, att, false)}
                      className="h-7 px-2 text-[11px]"
                    >
                      <Download className="size-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/** 详情页加载骨架 */
export function InboxMessageSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-6 w-2/3" />
      </div>
      <Card className="py-3">
        <CardContent className="px-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-2">
                <Skeleton className="h-4 w-14" />
                <Skeleton className="h-4 flex-1" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="py-3">
        <CardContent className="px-4">
          <Skeleton className="h-[400px] w-full" />
        </CardContent>
      </Card>
    </div>
  )
}
