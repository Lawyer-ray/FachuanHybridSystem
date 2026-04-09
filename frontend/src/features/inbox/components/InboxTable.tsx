import { useNavigate } from 'react-router'
import { Inbox, Paperclip } from 'lucide-react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { generatePath } from '@/routes/paths'
import type { InboxMessage } from '../types'

export interface InboxTableProps {
  messages: InboxMessage[]
  isLoading?: boolean
}

const SOURCE_COLORS: Record<string, string> = {
  imap: 'bg-blue-500',
  court_inbox: 'bg-purple-500',
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  const isThisYear = d.getFullYear() === now.getFullYear()
  if (isThisYear) return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <TableRow key={i}>
          {Array.from({ length: 5 }).map((_, j) => (
            <TableCell key={j}><div className="bg-muted h-4 w-24 animate-pulse rounded" /></TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}

function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={6} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <Inbox className="text-muted-foreground size-6" />
          </div>
          <p className="text-muted-foreground text-sm">暂无消息</p>
        </div>
      </TableCell>
    </TableRow>
  )
}

export function InboxTable({ messages, isLoading }: InboxTableProps) {
  const navigate = useNavigate()

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px]">来源</TableHead>
            <TableHead>主题</TableHead>
            <TableHead className="w-[180px]">发件人</TableHead>
            <TableHead className="w-[120px]">收件人</TableHead>
            <TableHead className="w-[140px]">时间</TableHead>
            <TableHead className="w-[70px] text-center">附件</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : messages.length === 0 ? (
            <EmptyState />
          ) : (
            messages.map((msg) => (
              <TableRow
                key={msg.id}
                className="cursor-pointer"
                onClick={() => navigate(generatePath.inboxDetail(msg.id))}
              >
                <TableCell>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium text-white ${SOURCE_COLORS[msg.source_type] ?? 'bg-gray-500'}`}
                  >
                    {msg.source_name}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="line-clamp-1 max-w-[300px]">{msg.subject || '(无主题)'}</span>
                </TableCell>
                <TableCell>
                  <span className="text-muted-foreground line-clamp-1 text-sm">{msg.sender || '-'}</span>
                </TableCell>
                <TableCell>
                  <span className="text-muted-foreground text-sm">{msg.recipient}</span>
                </TableCell>
                <TableCell>
                  <span className="text-muted-foreground text-sm">{formatTime(msg.received_at)}</span>
                </TableCell>
                <TableCell className="text-center">
                  {msg.has_attachments ? (
                    <Badge variant="secondary" className="gap-1">
                      <Paperclip className="size-3" />
                      {msg.attachment_count}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground/40">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
