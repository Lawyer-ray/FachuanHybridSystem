import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { formatDate } from '@/lib/date'
import { Search, Plus, Trash2, Loader2, LinkIcon } from 'lucide-react'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useCourtSmsList } from '../hooks/use-court-sms'
import { courtSmsApi } from '../api/court-sms'
import { caseApi } from '@/features/cases/api'
import { generatePath } from '@/routes/paths'

// ============================================================================
// Constants
// ============================================================================

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

// ============================================================================
// Sub-components
// ============================================================================

/** 案件搜索与关联对话框 */
function AssignCaseDialog({
  open,
  onOpenChange,
  smsId,
  smsContent,
  onSuccess,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  smsId: number | null
  smsContent: string
  onSuccess: () => void
}) {
  const [query, setQuery] = useState('')
  const [assigning, setAssigning] = useState<number | null>(null)

  const { data: searchResults, isFetching } = useQuery({
    queryKey: ['case-search', query],
    queryFn: () => caseApi.search(query, 15),
    enabled: open && query.length >= 1,
    staleTime: 10_000,
  })

  const cases = searchResults ?? []

  const handleAssign = async (caseId: number) => {
    if (!smsId) return
    setAssigning(caseId)
    try {
      await courtSmsApi.assignCase(smsId, caseId)
      onSuccess()
      onOpenChange(false)
    } catch (e) {
      console.error('Assign case failed:', e)
    } finally {
      setAssigning(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>关联案件</DialogTitle>
          <DialogDescription>搜索并选择要关联的案件</DialogDescription>
        </DialogHeader>

        {smsContent && (
          <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground line-clamp-2">
            {smsContent}
          </div>
        )}

        <div className="relative">
          <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input
            placeholder="输入案件名称、案号或当事人搜索..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
            autoFocus
          />
        </div>

        <div className="max-h-[300px] overflow-y-auto space-y-1">
          {isFetching && query.length >= 1 && (
            <div className="py-6 text-center text-muted-foreground text-sm">搜索中...</div>
          )}
          {!isFetching && query.length >= 1 && cases.length === 0 && (
            <div className="py-6 text-center text-muted-foreground text-sm">未找到匹配案件</div>
          )}
          {!isFetching && query.length < 1 && (
            <div className="py-6 text-center text-muted-foreground text-sm">输入关键词开始搜索</div>
          )}
          {cases.map((c) => (
            <div
              key={c.id}
              className="flex items-center justify-between rounded-md border p-3 hover:bg-muted/50 transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="font-medium text-sm truncate">{c.name}</div>
                {c.case_numbers && c.case_numbers.length > 0 && (
                  <div className="text-muted-foreground text-xs mt-0.5">
                    {c.case_numbers[0].number}
                  </div>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                className="ml-3 shrink-0"
                disabled={assigning === c.id}
                onClick={() => handleAssign(c.id)}
              >
                {assigning === c.id ? '关联中...' : '关联'}
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function CourtSmsTool() {
  const navigate = useNavigate()

  // Filter state
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [smsTypeFilter, setSmsTypeFilter] = useState<string>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // Submit dialog state
  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitContent, setSubmitContent] = useState('')
  const [submitReceivedAt, setSubmitReceivedAt] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [batchLoading, setBatchLoading] = useState(false)

  // Assign case dialog state
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignSmsId, setAssignSmsId] = useState<number | null>(null)
  const [assignSmsContent, setAssignSmsContent] = useState('')

  const queryClient = useQueryClient()
  const { data, isLoading } = useCourtSmsList({
    status: statusFilter === 'all' ? undefined : statusFilter,
    sms_type: smsTypeFilter === 'all' ? undefined : smsTypeFilter,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  })
  const items = data?.items ?? []

  const filtered = search
    ? items.filter((sms) =>
        sms.content.toLowerCase().includes(search.toLowerCase()) ||
        (sms.case_name && sms.case_name.toLowerCase().includes(search.toLowerCase()))
      )
    : items

  // Selection handlers
  const toggleRow = useCallback((id: number, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    const allIds = filtered.map((s) => s.id)
    const allSelected = allIds.length > 0 && allIds.every((id) => selectedIds.has(id))
    setSelectedIds(allSelected ? new Set() : new Set(allIds))
  }, [filtered, selectedIds])

  // Delete handlers
  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size === 0) return
    setBatchLoading(true)
    try {
      const ids = Array.from(selectedIds)
      await courtSmsApi.deleteBatch(ids)
      toast.success(`已删除 ${ids.length} 条短信`)
      setSelectedIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['court-sms'] })
    } catch {
      toast.error('批量删除失败')
    } finally {
      setBatchLoading(false)
    }
  }, [selectedIds, queryClient])

  const handleSubmit = async () => {
    if (!submitContent.trim()) return
    setSubmitting(true)
    try {
      await courtSmsApi.submit(
        submitContent.trim(),
        submitReceivedAt || undefined,
      )
      setSubmitOpen(false)
      setSubmitContent('')
      setSubmitReceivedAt('')
      queryClient.invalidateQueries({ queryKey: ['court-sms'] })
    } catch (e) {
      console.error('Submit failed:', e)
    } finally {
      setSubmitting(false)
    }
  }

  const handleOpenAssign = useCallback((id: number, content: string) => {
    setAssignSmsId(id)
    setAssignSmsContent(content)
    setAssignOpen(true)
  }, [])

  const handleAssignSuccess = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['court-sms'] })
  }, [queryClient])

  const colCount = 7 // checkbox + ID + 状态 + 内容 + 关联案件 + 文书 + 收到时间

  return (
    <div className="space-y-6">
      {/* Header */}
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
      <div className="flex flex-wrap items-end gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input
            type="text"
            placeholder="搜索内容或案件名称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* SMS Type filter */}
        <Select value={smsTypeFilter} onValueChange={setSmsTypeFilter}>
          <SelectTrigger className="w-[130px] h-9">
            <SelectValue placeholder="短信类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            {Object.entries(SMS_TYPE_LABELS).map(([v, l]) => (
              <SelectItem key={v} value={v}>{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Date from */}
        <div className="flex items-center gap-1.5">
          <Label htmlFor="date-from" className="text-xs text-muted-foreground whitespace-nowrap">从</Label>
          <Input
            id="date-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 w-[140px]"
          />
        </div>

        {/* Date to */}
        <div className="flex items-center gap-1.5">
          <Label htmlFor="date-to" className="text-xs text-muted-foreground whitespace-nowrap">至</Label>
          <Input
            id="date-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="h-9 w-[140px]"
          />
        </div>

        {/* Clear filters */}
        {(smsTypeFilter !== 'all' || dateFrom || dateTo) && (
          <Button
            variant="ghost"
            size="sm"
            className="h-9 text-xs"
            onClick={() => { setSmsTypeFilter('all'); setDateFrom(''); setDateTo('') }}
          >
            清除筛选
          </Button>
        )}
      </div>

      {/* Status filter buttons */}
      <div className="flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((s) => (
          <Button
            key={s}
            variant={s === statusFilter ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(s)}
            className="h-8 text-xs"
          >
            {s === 'all' ? '全部' : STATUS_LABELS[s] ?? s}
          </Button>
        ))}
      </div>

      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/50 px-4 py-2">
          <span className="text-sm text-muted-foreground">
            已选 <span className="font-medium text-foreground">{selectedIds.size}</span> 项
          </span>
          <div className="flex-1" />
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            disabled={batchLoading}
            onClick={handleBatchDelete}
          >
            {batchLoading ? <Loader2 className="mr-1 size-3 animate-spin" /> : <Trash2 className="mr-1 size-3" />}
            删除选中
          </Button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[40px]">
                <Checkbox
                  checked={filtered.length > 0 && filtered.every((s) => selectedIds.has(s.id))}
                  onCheckedChange={toggleAll}
                  aria-label="全选"
                />
              </TableHead>
              <TableHead className="w-[60px]">ID</TableHead>
              <TableHead className="w-[90px]">状态</TableHead>
              <TableHead>短信内容</TableHead>
              <TableHead className="w-[160px]">关联案件</TableHead>
              <TableHead className="w-[60px]">文书</TableHead>
              <TableHead className="w-[120px]">收到时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: colCount }).map((_, j) => (
                    <TableCell key={j}><div className="bg-muted h-4 w-20 animate-pulse rounded" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={colCount} className="h-32 text-center text-muted-foreground text-sm">
                  没有短信记录
                </TableCell>
              </TableRow>
            ) : filtered.map((sms) => {
              const statusLabel = STATUS_LABELS[sms.status] ?? sms.status
              const variant = STATUS_BADGE_VARIANT[sms.status] ?? 'outline'

              return (
                <TableRow key={sms.id}>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(sms.id)}
                      onCheckedChange={() => toggleRow(sms.id)}
                      aria-label={`选择短信 #${sms.id}`}
                    />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{sms.id}</TableCell>
                  <TableCell>
                    <Badge variant={variant} className="text-xs">{statusLabel}</Badge>
                  </TableCell>
                  <TableCell
                    className="text-sm max-w-[400px] truncate cursor-pointer hover:text-primary"
                    title={sms.content}
                    onClick={() => navigate(generatePath.courtSmsDetail(sms.id))}
                  >
                    {sms.content}
                  </TableCell>
                  <TableCell className="text-sm truncate max-w-[160px]" title={sms.case_name ?? undefined}>
                    {sms.case_name || (
                      sms.status === 'pending_manual' ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-1.5 text-xs text-primary"
                          onClick={(e) => { e.stopPropagation(); handleOpenAssign(sms.id, sms.content) }}
                        >
                          <LinkIcon className="size-3 mr-0.5" />手动关联
                        </Button>
                      ) : '-'
                    )}
                  </TableCell>
                  <TableCell className="text-sm">
                    {sms.has_documents ? <span className="text-green-600">有</span> : '-'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {formatDate(sms.received_at)}
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
          <div className="space-y-4">
            <div>
              <Label htmlFor="sms-content">短信内容</Label>
              <Textarea
                id="sms-content"
                placeholder="粘贴短信内容..."
                value={submitContent}
                onChange={(e) => setSubmitContent(e.target.value)}
                rows={6}
                className="mt-1.5"
              />
            </div>
            <div>
              <Label htmlFor="received-at">收到时间（可选）</Label>
              <Input
                id="received-at"
                type="datetime-local"
                value={submitReceivedAt}
                onChange={(e) => setSubmitReceivedAt(e.target.value)}
                className="mt-1.5"
              />
              <p className="text-muted-foreground text-xs mt-1">留空则使用当前时间</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSubmitOpen(false)}>取消</Button>
            <Button onClick={handleSubmit} disabled={!submitContent.trim() || submitting}>
              {submitting ? '提交中...' : '提交'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assign Case Dialog */}
      <AssignCaseDialog
        open={assignOpen}
        onOpenChange={setAssignOpen}
        smsId={assignSmsId}
        smsContent={assignSmsContent}
        onSuccess={handleAssignSuccess}
      />
    </div>
  )
}
