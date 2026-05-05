import { useState } from 'react'
import { Search, Plus, Eye, Link2, RotateCcw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { useCourtSmsList } from '../hooks/use-court-sms'
import { courtSmsApi, type CourtSMSDetail } from '../api/court-sms'

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理', parsing: '解析中', downloading: '下载中',
  download_failed: '下载失败', matching: '匹配中', pending_manual: '待人工处理',
  renaming: '重命名中', notifying: '通知中', completed: '已完成', failed: '处理失败',
}

const STATUS_BADGE_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  completed: 'default', pending_manual: 'secondary', download_failed: 'destructive', failed: 'destructive',
}

const SMS_TYPE_LABELS: Record<string, string> = {
  document_delivery: '文书送达', info_notification: '信息通知', filing_notification: '立案通知',
}

const STATUS_FILTERS = ['all', 'completed', 'pending_manual', 'download_failed', 'failed'] as const

export function CourtSmsTool() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitContent, setSubmitContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<CourtSMSDetail | null>(null)

  const queryClient = useQueryClient()
  const { data, isLoading } = useCourtSmsList({
    status: statusFilter === 'all' ? undefined : statusFilter,
  })
  const items = data?.items ?? []

  const filtered = search
    ? items.filter((sms) =>
        sms.content.toLowerCase().includes(search.toLowerCase()) ||
        (sms.case_name && sms.case_name.toLowerCase().includes(search.toLowerCase()))
      )
    : items

  const handleSubmit = async () => {
    if (!submitContent.trim()) return
    setSubmitting(true)
    try {
      await courtSmsApi.submit(submitContent.trim())
      setSubmitOpen(false)
      setSubmitContent('')
      queryClient.invalidateQueries({ queryKey: ['court-sms'] })
    } catch (e) {
      console.error('Submit failed:', e)
    } finally {
      setSubmitting(false)
    }
  }

  const handleView = async (id: number) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    try {
      const data = await courtSmsApi.get(id)
      setDetail(data)
    } catch (e) {
      console.error('Fetch detail failed:', e)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleRetry = async (id: number) => {
    if (!window.confirm('确定重新处理此短信？')) return
    try {
      await courtSmsApi.retry(id)
      queryClient.invalidateQueries({ queryKey: ['court-sms'] })
    } catch (e) {
      console.error('Retry failed:', e)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">法院短信</h1>
          <p className="text-muted-foreground text-sm mt-1">自动解析法院送达短信，关联案件并下载文书</p>
        </div>
        <Button size="sm" onClick={() => setSubmitOpen(true)}>
          <Plus className="mr-1.5 size-4" />提交短信
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input type="text" placeholder="搜索内容或案件名称..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        {STATUS_FILTERS.map((s) => (
          <Button key={s} variant={s === statusFilter ? 'default' : 'outline'} size="sm" onClick={() => setStatusFilter(s)} className="h-8 text-xs">
            {s === 'all' ? '全部' : STATUS_LABELS[s] ?? s}
          </Button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60px]">ID</TableHead>
              <TableHead className="w-[90px]">状态</TableHead>
              <TableHead>短信内容</TableHead>
              <TableHead className="w-[160px]">关联案件</TableHead>
              <TableHead className="w-[60px]">文书</TableHead>
              <TableHead className="w-[120px]">收到时间</TableHead>
              <TableHead className="w-[70px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <TableCell key={j}><div className="bg-muted h-4 w-20 animate-pulse rounded" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center text-muted-foreground text-sm">没有短信记录</TableCell>
              </TableRow>
            ) : filtered.map((sms) => {
              const statusLabel = STATUS_LABELS[sms.status] ?? sms.status
              const variant = STATUS_BADGE_VARIANT[sms.status] ?? 'outline'

              return (
                <TableRow key={sms.id}>
                  <TableCell className="text-muted-foreground text-sm">{sms.id}</TableCell>
                  <TableCell><Badge variant={variant} className="text-xs">{statusLabel}</Badge></TableCell>
                  <TableCell className="text-sm max-w-[400px] truncate" title={sms.content}>{sms.content}</TableCell>
                  <TableCell className="text-sm truncate max-w-[160px]" title={sms.case_name ?? undefined}>{sms.case_name || '-'}</TableCell>
                  <TableCell className="text-sm">{sms.has_documents ? <span className="text-status-green">有</span> : '-'}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{sms.received_at ? new Date(sms.received_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleView(sms.id)}>
                        <Eye className="size-3 mr-0.5" />查看
                      </Button>
                      {(sms.status === 'failed' || sms.status === 'download_failed') && (
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleRetry(sms.id)}>
                          <RotateCcw className="size-3" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Submit Dialog */}
      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>提交短信</DialogTitle>
            <DialogDescription>粘贴法院短信内容，系统将自动解析并处理</DialogDescription>
          </DialogHeader>
          <Textarea
            placeholder="粘贴短信内容..."
            value={submitContent}
            onChange={(e) => setSubmitContent(e.target.value)}
            rows={6}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setSubmitOpen(false)}>取消</Button>
            <Button onClick={handleSubmit} disabled={!submitContent.trim() || submitting}>
              {submitting ? '提交中...' : '提交'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>短信详情 #{detail?.id}</DialogTitle>
          </DialogHeader>
          {detailLoading ? (
            <div className="space-y-3 py-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-muted h-4 w-full animate-pulse rounded" />
              ))}
            </div>
          ) : detail && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Badge variant={STATUS_BADGE_VARIANT[detail.status] ?? 'outline'} className="text-xs">
                  {STATUS_LABELS[detail.status] ?? detail.status}
                </Badge>
                {detail.sms_type && (
                  <Badge variant="outline" className="text-xs">
                    {SMS_TYPE_LABELS[detail.sms_type] ?? detail.sms_type}
                  </Badge>
                )}
              </div>

              <div className="rounded-md bg-muted p-4">
                <div className="text-xs text-muted-foreground mb-1">短信内容</div>
                <div className="text-sm whitespace-pre-wrap">{detail.content}</div>
              </div>

              {detail.case && (
                <div className="rounded-md bg-muted p-4">
                  <div className="text-xs text-muted-foreground mb-1">关联案件</div>
                  <div className="text-sm font-medium">{detail.case.name}</div>
                </div>
              )}

              {detail.case_numbers.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1.5">案号</div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.case_numbers.map((cn, i) => (
                      <Badge key={i} variant="secondary" className="text-xs">{cn}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {detail.party_names.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1.5">当事人</div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.party_names.map((pn, i) => (
                      <Badge key={i} variant="outline" className="text-xs">{pn}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {detail.documents.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1.5">文书</div>
                  <div className="space-y-1.5">
                    {detail.documents.map((doc) => (
                      <div key={doc.id} className="flex items-center gap-2 text-sm bg-muted rounded-md px-3 py-2">
                        <Link2 className="size-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate">{doc.name}</span>
                        {doc.download_url && (
                          <a href={doc.download_url} target="_blank" rel="noopener noreferrer" className="ml-auto text-primary text-xs hover:underline shrink-0">
                            下载
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.download_links.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1.5">下载链接</div>
                  <div className="space-y-1">
                    {detail.download_links.map((url, i) => (
                      <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="block text-xs text-primary hover:underline truncate">
                        {url}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {detail.error_message && (
                <div className="rounded-md bg-destructive/10 p-3">
                  <div className="text-xs text-destructive font-medium mb-1">错误信息</div>
                  <div className="text-xs text-destructive">{detail.error_message}</div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground pt-2 border-t">
                <div>收到时间: {detail.received_at ? new Date(detail.received_at).toLocaleString('zh-CN') : '-'}</div>
                <div>创建时间: {new Date(detail.created_at).toLocaleString('zh-CN')}</div>
                {detail.feishu_sent_at && <div>飞书通知: {new Date(detail.feishu_sent_at).toLocaleString('zh-CN')}</div>}
                {detail.retry_count > 0 && <div>重试次数: {detail.retry_count}</div>}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
