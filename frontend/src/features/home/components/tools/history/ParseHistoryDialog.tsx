import { useState } from 'react'
import { ArrowLeft, Copy, FileDown } from 'lucide-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'

import { getParseRecord, listParseRecords } from '../../../api'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { BTN, BTN_PRIMARY } from '../../../ui'
import { FlowNotice } from '../dialog/TaskFlowDialog'
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

/**
 * 文档解析历史弹窗：同一弹窗内「列表 ⇄ 详情」切换（不叠第二层弹窗）——
 * 点某条进入详情看全文（复制/下载与结果弹窗同款），「← 返回」回列表。
 */
export function ParseHistoryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [group, setGroup] = useState('')
  const [page, setPage] = useState(1)
  // 非 null 时弹窗处于详情视图
  const [detailId, setDetailId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['doc-parse-history', group, page],
    queryFn: () => listParseRecords(group || undefined, page),
    enabled: open,
    staleTime: 10_000,
    // 翻页/切组时保留上一屏数据，避免列表闪「正在加载…」、弹窗高度跳动
    placeholderData: keepPreviousData,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['doc-parse-record', detailId],
    queryFn: () => getParseRecord(detailId!),
    enabled: detailId !== null && open,
    staleTime: 60_000,
  })

  const closeAll = () => {
    // 关闭弹窗即回到列表视图，下次打开从头开始
    setDetailId(null)
    onOpenChange(false)
  }

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / 20))

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
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) closeAll()
        else onOpenChange(o)
      }}
    >
      <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
        {detailId === null ? (
          /* ───── 列表视图 ───── */
          <>
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
                <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">这个筛选下没有记录</div>
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
          </>
        ) : (
          /* ───── 详情视图 ───── */
          <>
            <div className="flex flex-none items-center gap-2.5 border-b border-border px-3 py-3 pr-10">
              <button
                type="button"
                onClick={() => setDetailId(null)}
                className="flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <ArrowLeft className="h-3 w-3" />
                返回
              </button>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold" title={detail?.file_name}>
                  {detail?.file_name ?? '正在载入…'}
                </div>
                {detail && (
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                    <span className={cn('rounded-[6px] border px-1.5 py-[1px] text-[10px] font-semibold', badgeOf(detail.status))}>
                      {STATUS_LABEL[detail.status] ?? detail.status}
                    </span>
                    <span>{format(new Date(detail.created_at), 'MM-dd HH:mm')}</span>
                    {detail.backend_used && <span>· {detail.backend_used}</span>}
                  </div>
                )}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {detailLoading || !detail ? (
                <div className="py-8 text-center text-[12px] text-muted-foreground">正在载入记录…</div>
              ) : ok && outcome ? (
                <pre className="min-h-0 overflow-auto rounded-[10px] border border-border bg-background px-3 py-2.5 text-[11.5px] leading-[1.7] whitespace-pre-wrap break-all">
                  {outcome.markdown || outcome.text || '（解析结果为空）'}
                </pre>
              ) : (
                <FlowNotice kind="error">{detail.error_message || '该次解析失败'}</FlowNotice>
              )}
            </div>

            <div className="flex flex-none items-center justify-end gap-2 border-t border-border px-4 py-2.5">
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
              <button type="button" className={ok ? BTN : BTN_PRIMARY} onClick={closeAll}>
                关闭
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
