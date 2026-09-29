import { useState } from 'react'
import { Copy, FileDown, History } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'

import { getParseRecord, listParseRecords, type ParseRecordDetail } from '../../../api'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { BTN, BTN_PRIMARY } from '../../../ui'
import { FlowNotice, TaskFlowDialog } from '../dialog/TaskFlowDialog'
import { copyOutcome, downloadOutcome } from '../doc-parse-outcome'
import { badgeOf } from './badges'
import { HistoryHeader, HistoryPager } from './HistoryParts'

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  processing: '解析中',
  completed: '已完成',
  failed: '失败',
}

const GROUPS = [
  { value: '', label: '全部' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
] as const

/** 文档解析历史弹窗：列表点开 → 详情弹窗看全文（复制 / 下载与结果弹窗同款） */
export function ParseHistoryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [group, setGroup] = useState<string>('')
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['doc-parse-history', group, page],
    queryFn: () => listParseRecords(group || undefined, page),
    enabled: open,
    staleTime: 10_000,
  })

  const { data: detail } = useQuery({
    queryKey: ['doc-parse-record', detailId],
    queryFn: () => getParseRecord(detailId!),
    enabled: detailId !== null,
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / 20))

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
          <HistoryHeader title="历史解析" count={count}>
            <div className="flex items-center gap-1">
              {GROUPS.map((g) => (
                <button
                  key={g.value}
                  type="button"
                  onClick={() => {
                    setGroup(g.value)
                    setPage(1)
                  }}
                  className={cn(
                    'rounded-[7px] px-2.5 py-[5px] text-[11.5px] font-medium transition-colors',
                    group === g.value
                      ? 'bg-foreground text-background'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                  )}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </HistoryHeader>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">正在加载…</div>
            ) : items.length === 0 ? (
              <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">
                这个筛选下没有记录
              </div>
            ) : (
              items.map((it) => (
                <button
                  key={it.id}
                  type="button"
                  onClick={() => setDetailId(it.id)}
                  className="flex w-full items-start gap-2.5 border-b border-border px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
                >
                  <span
                    className={cn(
                      'mt-[2px] flex-none rounded-[6px] border px-1.5 py-[1px] text-[10px] font-semibold whitespace-nowrap',
                      badgeOf(it.status),
                    )}
                  >
                    {STATUS_LABEL[it.status] ?? it.status}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 text-[12px] leading-snug font-medium text-foreground" title={it.file_name}>
                      {it.file_name}
                    </span>
                    <span className="mt-0.5 line-clamp-1 text-[10.5px] leading-snug text-muted-foreground">
                      {it.text_preview || (it.status === 'failed' ? it.error_message || '解析失败' : '（无预览）')}
                    </span>
                    <span className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                      <span>{format(new Date(it.created_at), 'MM-dd HH:mm')}</span>
                      {it.backend_used && (
                        <>
                          <span>·</span>
                          <span>{it.backend_used}</span>
                        </>
                      )}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>

          <HistoryPager page={page} totalPages={totalPages} onChange={setPage} />
        </DialogContent>
      </Dialog>

      <RecordDetailDialog
        detail={detail ?? null}
        loading={detailId !== null && !detail}
        onOpenChange={(o) => {
          if (!o) setDetailId(null)
        }}
      />
    </>
  )
}

/** 记录详情弹窗：全文预览 + 复制 / 下载（与解析结果弹窗同款操作） */
function RecordDetailDialog({
  detail,
  loading,
  onOpenChange,
}: {
  detail: ParseRecordDetail | null
  loading: boolean
  onOpenChange: (open: boolean) => void
}) {
  const open = detail !== null || loading
  const ok = detail?.status === 'completed'
  const outcome = detail
    ? {
        ok: detail.status === 'completed',
        markdown: detail.markdown ?? '',
        text: detail.text,
        method: detail.backend_used,
        error: detail.status === 'failed' ? detail.error_message : null,
        metadata: detail.metadata,
      }
    : null
  const baseName = (detail?.file_name ?? 'document').replace(/\.[^.]+$/, '')

  return (
    <TaskFlowDialog
      open={open}
      onOpenChange={onOpenChange}
      icon={<History className="h-5 w-5" />}
      title="历史解析"
      tone={loading || !detail ? 'running' : ok ? 'success' : 'error'}
      headline={loading || !detail ? '正在载入记录…' : ok ? '解析记录' : '解析失败记录'}
      subline={detail ? `${detail.file_name} · ${format(new Date(detail.created_at), 'MM-dd HH:mm')}` : undefined}
      wide={!!ok}
      footer={
        <>
          {ok && outcome && (
            <>
              <button type="button" className={BTN} onClick={() => void copyOutcome(outcome)}>
                <Copy className="h-3.5 w-3.5" />
                复制全文
              </button>
              <button type="button" className={BTN_PRIMARY} onClick={() => downloadOutcome(outcome, baseName)}>
                <FileDown className="h-3.5 w-3.5" />
                {outcome.markdown ? '下载 .md' : '下载 .txt'}
              </button>
            </>
          )}
          <button type="button" className={ok ? BTN : BTN_PRIMARY} onClick={() => onOpenChange(false)}>
            关闭
          </button>
        </>
      }
    >
      {ok && outcome && (
        <pre className="max-h-[320px] min-h-0 overflow-auto rounded-[10px] border border-border bg-background px-3 py-2.5 text-[11.5px] leading-[1.7] whitespace-pre-wrap break-all">
          {outcome.markdown || outcome.text || '（解析结果为空）'}
        </pre>
      )}
      {!loading && !ok && <FlowNotice kind="error">{detail?.error_message || '该次解析失败'}</FlowNotice>}
    </TaskFlowDialog>
  )
}
