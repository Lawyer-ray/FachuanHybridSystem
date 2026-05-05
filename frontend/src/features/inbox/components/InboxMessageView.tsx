import { useNavigate } from 'react-router'
import { ArrowLeft, Download, Eye, Paperclip, Mail, Link2, Bell, Forward, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS } from '@/routes/paths'
import { getAccessToken } from '@/lib/token'
import { inboxApi } from '../api'
import type { InboxMessageDetail, AttachmentMeta } from '../types'

const SOURCE_COLORS: Record<string, string> = {
  imap: 'bg-blue-500',
  court_inbox: 'bg-purple-500',
  court_schedule: 'bg-yellow-500',
}

const SOURCE_LABELS: Record<string, string> = {
  imap: 'IMAP 邮箱',
  court_inbox: '一张网收件箱',
  court_schedule: '一张网庭审日程',
}

import { formatDate } from '@/lib/date'

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

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <Button
          variant="ghost" size="sm"
          onClick={() => navigate(PATHS.ADMIN_INBOX)}
          className="gap-1"
        >
          <ArrowLeft className="size-4" />
          返回列表
        </Button>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">转发</Button>
          <Button variant="outline" size="sm" className="text-destructive border-destructive hover:text-destructive">
            删除
          </Button>
        </div>
      </div>

      {/* 主题信息栏 */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <h1 className="text-lg font-semibold leading-snug">
                {message.subject || '(无主题)'}
              </h1>
              <div className="flex items-center gap-4 mt-2.5 text-[13px] text-muted-foreground flex-wrap">
                <span>发件人：<strong className="text-foreground">{message.sender || '-'}</strong></span>
                <span>收件人：{message.recipient}</span>
                <span>{formatDate(message.received_at)}</span>
              </div>
            </div>
            <div className="flex gap-1.5 shrink-0">
              <Badge className={`${SOURCE_COLORS[message.source_type] ?? 'bg-gray-500'} text-white text-[11px]`}>
                {SOURCE_LABELS[message.source_type] || message.source_type}
              </Badge>
              {message.attachments.length > 0 && (
                <Badge variant="secondary" className="text-[11px]">
                  {message.attachments.length} 个附件
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 两栏布局：左侧正文 + 右侧信息面板 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4 items-start">
        {/* 左栏：正文 */}
        <Card>
          <CardHeader className="py-3 px-4 border-b border-border">
            <CardTitle className="flex items-center gap-2 text-[13px] font-semibold">
              <Mail className="size-4" />
              邮件正文
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {message.body_html ? (
              <iframe
                srcDoc={message.body_html}
                sandbox=""
                className="w-full bg-white rounded-b-lg"
                style={{ minHeight: 500, height: 'auto' }}
                onLoad={(e) => {
                  const iframe = e.currentTarget
                  const doc = iframe.contentDocument
                  if (doc?.body) {
                    iframe.style.height = `${doc.body.scrollHeight + 32}px`
                  }
                }}
              />
            ) : message.body_text ? (
              <div className="whitespace-pre-wrap text-sm leading-relaxed p-6">
                {message.body_text}
              </div>
            ) : (
              <div className="text-muted-foreground text-sm text-center py-16">
                无正文内容
              </div>
            )}
          </CardContent>
        </Card>

        {/* 右栏：信息面板 */}
        <div className="flex flex-col gap-4">
          {/* 消息信息 */}
          <Card>
            <CardHeader className="py-3 px-4 border-b border-border">
              <CardTitle className="text-[13px] font-semibold">消息信息</CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-3 space-y-2.5 text-[13px]">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">来源</span>
                <Badge className={`${SOURCE_COLORS[message.source_type] ?? 'bg-gray-500'} text-white text-[11px]`}>
                  {SOURCE_LABELS[message.source_type] || message.source_type}
                </Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">来源名称</span>
                <span>{message.source_name}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">收件人</span>
                <span className="truncate ml-2">{message.recipient}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">原始 ID</span>
                <span className="font-mono text-xs truncate ml-2">{message.message_id}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">接收时间</span>
                <span>{formatDate(message.received_at)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">入库时间</span>
                <span>{formatDate(message.created_at)}</span>
              </div>
            </CardContent>
          </Card>

          {/* 附件 */}
          <Card>
            <CardHeader className="py-3 px-4 border-b border-border">
              <CardTitle className="flex items-center gap-2 text-[13px] font-semibold">
                <Paperclip className="size-3.5" />
                附件 ({message.attachments.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-3">
              {message.attachments.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {message.attachments.map((att) => (
                    <div
                      key={att.part_index}
                      className="flex items-center gap-2.5 p-2.5 rounded-md bg-muted/50 border border-border"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-medium truncate">{att.filename}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {formatSize(att.size)} · {att.content_type || '未知类型'}
                        </p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        {canPreview(att.content_type) && (
                          <Button
                            variant="outline" size="sm"
                            onClick={() => openAttachment(message.id, att, true)}
                            className="h-7 px-2 text-[11px]"
                          >
                            <Eye className="size-3" />
                          </Button>
                        )}
                        <Button
                          variant="outline" size="sm"
                          onClick={() => openAttachment(message.id, att, false)}
                          className="h-7 px-2 text-[11px]"
                        >
                          <Download className="size-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Button variant="outline" size="sm" className="w-full mt-1 text-[12px]">
                    <Download className="mr-1.5 size-3.5" />
                    全部下载
                  </Button>
                </div>
              ) : (
                <div className="text-muted-foreground text-[13px]">无附件</div>
              )}
            </CardContent>
          </Card>

          {/* 快速操作 */}
          <Card>
            <CardHeader className="py-3 px-4 border-b border-border">
              <CardTitle className="text-[13px] font-semibold">快速操作</CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-3">
              <div className="grid grid-cols-2 gap-1.5">
                <Button variant="outline" size="sm" className="text-[12px] justify-center">
                  <Link2 className="mr-1 size-3.5" />
                  匹配关联案件
                </Button>
                <Button variant="outline" size="sm" className="text-[12px] justify-center">
                  <Bell className="mr-1 size-3.5" />
                  创建提醒
                </Button>
                <Button variant="outline" size="sm" className="text-[12px] justify-center">
                  <Forward className="mr-1 size-3.5" />
                  转发到飞书群
                </Button>
                <Button variant="outline" size="sm" className="text-[12px] justify-center">
                  <CheckCircle2 className="mr-1 size-3.5" />
                  标记已处理
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

/** 详情页加载骨架 */
export function InboxMessageSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-8 w-24" />
      <Card>
        <CardContent className="pt-6">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="mt-2 h-4 w-1/2" />
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-[500px] w-full" />
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <CardContent className="pt-6">
              <Skeleton className="h-40 w-full" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <Skeleton className="h-24 w-full" />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
