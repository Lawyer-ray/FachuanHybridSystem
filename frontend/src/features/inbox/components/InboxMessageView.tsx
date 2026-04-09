import { useNavigate } from 'react-router'
import { ArrowLeft, Download, Eye, Paperclip, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { PATHS } from '@/routes/paths'
import { getAccessToken } from '@/lib/token'
import { inboxApi } from '../api'
import type { InboxMessageDetail, AttachmentMeta } from '../types'

const SOURCE_COLORS: Record<string, string> = {
  imap: 'bg-blue-500',
  court_inbox: 'bg-purple-500',
}

function formatDateTime(iso: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function canPreview(contentType: string): boolean {
  return contentType.includes('pdf') || contentType.startsWith('image/')
}

/** 带 token 的附件操作 */
function openAttachment(messageId: number, att: AttachmentMeta, inline: boolean) {
  const url = inline
    ? inboxApi.attachmentPreviewUrl(messageId, att.part_index)
    : inboxApi.attachmentDownloadUrl(messageId, att.part_index)
  const token = getAccessToken()
  // 通过 fetch + blob 下载（因为需要 Authorization header）
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
    .catch(() => {
      // 静默失败，可以加 toast
    })
}

interface Props {
  message: InboxMessageDetail
}

export function InboxMessageView({ message }: Props) {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col gap-6">
      {/* 返回按钮 */}
      <Button
        variant="ghost" size="sm"
        onClick={() => navigate(PATHS.ADMIN_INBOX)}
        className="w-fit gap-2"
      >
        <ArrowLeft className="size-4" />
        返回收件箱
      </Button>

      {/* 消息头部 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-2">
              <CardTitle className="text-xl">{message.subject || '(无主题)'}</CardTitle>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium text-white ${SOURCE_COLORS[message.source_type] ?? 'bg-gray-500'}`}
                >
                  {message.source_name}
                </span>
                <span className="text-muted-foreground">
                  发件人：{message.sender || '-'}
                </span>
                <span className="text-muted-foreground">
                  收件人：{message.recipient}
                </span>
                <span className="text-muted-foreground">
                  {formatDateTime(message.received_at)}
                </span>
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* 正文 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Mail className="size-4" />
            正文
          </CardTitle>
        </CardHeader>
        <CardContent>
          {message.body_html ? (
            <iframe
              srcDoc={message.body_html}
              sandbox=""
              className="w-full rounded border bg-white"
              style={{ minHeight: 300, height: 'auto' }}
              onLoad={(e) => {
                const iframe = e.currentTarget
                const doc = iframe.contentDocument
                if (doc?.body) {
                  iframe.style.height = `${doc.body.scrollHeight + 32}px`
                }
              }}
            />
          ) : message.body_text ? (
            <div className="max-h-[600px] overflow-auto whitespace-pre-wrap rounded border bg-white p-4 text-sm dark:bg-gray-950">
              {message.body_text}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">无正文内容</p>
          )}
        </CardContent>
      </Card>

      {/* 附件 */}
      {message.attachments.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Paperclip className="size-4" />
              附件（{message.attachments.length}）
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {message.attachments.map((att) => (
                <div
                  key={att.part_index}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium">{att.filename}</p>
                    <p className="text-muted-foreground text-xs">{formatSize(att.size)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {canPreview(att.content_type) && (
                      <Button
                        variant="outline" size="sm"
                        onClick={() => openAttachment(message.id, att, true)}
                        className="gap-1"
                      >
                        <Eye className="size-3.5" />
                        预览
                      </Button>
                    )}
                    <Button
                      variant="outline" size="sm"
                      onClick={() => openAttachment(message.id, att, false)}
                      className="gap-1"
                    >
                      <Download className="size-3.5" />
                      下载
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
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-24" />
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="mt-2 h-4 w-1/2" />
        </CardHeader>
      </Card>
      <Card>
        <CardHeader><Skeleton className="h-5 w-20" /></CardHeader>
        <CardContent><Skeleton className="h-48 w-full" /></CardContent>
      </Card>
    </div>
  )
}
