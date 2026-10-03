import { useState } from 'react'
import { ArrowLeft, CheckCircle2, FileDown, XCircle } from 'lucide-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'

import {
  converterHistoryKeys,
  converterDownloadUrl,
  converterItemDownloadUrl,
  getConverterJob,
  listConverterJobs,
  triggerDownload,
  type ConverterJobItem,
} from '../../../api'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { BTN, BTN_PRIMARY } from '../../../ui'
import { FlowNotice } from '../dialog/TaskFlowDialog'
import { badgeOf } from './badges'
import { HistoryHeader, HistoryPager } from './HistoryParts'

const STATUS_LABEL: Record<string, string> = {
  pending: '排队中',
  converting: '转换中',
  packing: '打包中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground'

/**
 * DOC 转 DOCX 历史弹窗：同一弹窗内「列表 ⇄ 任务详情」切换（不叠第二层弹窗）——
 * 点某单任务进入详情逐件下载 / 打包 ZIP，「← 返回」回列表。
 */
export function ConverterHistoryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [page, setPage] = useState(1)
  // 非 null 时弹窗处于任务详情视图
  const [pickedId, setPickedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: converterHistoryKeys.page(page),
    queryFn: () => listConverterJobs(page),
    enabled: open,
    staleTime: 10_000,
    // 翻页时保留上一页数据，避免列表闪「正在加载…」、弹窗高度跳动
    placeholderData: keepPreviousData,
  })

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: converterHistoryKeys.job(pickedId),
    queryFn: () => getConverterJob(pickedId!),
    enabled: pickedId !== null && open,
    staleTime: 60_000,
  })

  const closeAll = () => {
    setPickedId(null)
    onOpenChange(false)
  }

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / 20))
  const okItems = (job?.items ?? []).filter((it) => it.ok)
  const jobId = pickedId

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) closeAll()
        else onOpenChange(o)
      }}
    >
      <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
        {pickedId === null ? (
          /* ───── 列表视图 ───── */
          <>
            <HistoryHeader title="DOC 转 DOCX 历史" count={count} />

            <div className="min-h-0 flex-1 overflow-y-auto">
              {isLoading ? (
                <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">正在加载…</div>
              ) : items.length === 0 ? (
                <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">还没有转换任务</div>
              ) : (
                items.map((it) => <JobRow key={it.id} item={it} onPick={() => setPickedId(it.id)} />)
              )}
            </div>

            <HistoryPager page={page} totalPages={totalPages} onChange={setPage} />
          </>
        ) : (
          /* ───── 任务详情视图 ───── */
          <>
            <div className="flex flex-none items-center gap-2.5 border-b border-border px-3 py-3 pr-10">
              <button
                type="button"
                onClick={() => setPickedId(null)}
                className="flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <ArrowLeft className="h-3 w-3" />
                返回
              </button>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold">转换任务</div>
                {job && (
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                    <span className={cn('rounded-[6px] border px-1.5 py-[1px] text-[10px] font-semibold', badgeOf(job.status))}>
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>
                    <span>
                      共 {job.total} 件 · 成功 {job.done}
                      {job.failed > 0 ? ` · 失败 ${job.failed}` : ''}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {jobLoading || !job ? (
                <div className="py-8 text-center text-[12px] text-muted-foreground">正在载入记录…</div>
              ) : job.done > 0 ? (
                <div className="flex flex-col gap-2">
                  {okItems.map((it) => (
                    <div
                      key={it.id}
                      className="flex items-center gap-2.5 rounded-[10px] border border-border bg-secondary/40 px-3 py-2 transition-colors hover:bg-secondary/70"
                    >
                      <CheckCircle2 className="h-4 w-4 flex-none text-status-green" />
                      <span className="min-w-0 flex-1 truncate text-[12px] font-medium" title={it.name}>
                        {it.name}
                      </span>
                      <button type="button" className={ROW_BTN} onClick={() => triggerDownload(converterItemDownloadUrl(jobId!, it.id))}>
                        <FileDown className="h-3 w-3" />
                        下载
                      </button>
                    </div>
                  ))}
                  {job.failed > 0 && (
                    <div className="flex flex-col gap-1">
                      <div className="text-[11px] font-semibold text-status-red">失败 {job.failed} 件</div>
                      {job.items
                        .filter((it) => !it.ok)
                        .map((it) => (
                          <div key={it.id} className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
                            <XCircle className="h-3.5 w-3.5 flex-none text-status-red" />
                            <span className="min-w-0 flex-1 truncate">{it.name}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              ) : (
                <FlowNotice kind="error">该任务没有转换成功的文件</FlowNotice>
              )}
            </div>

            <div className="flex flex-none items-center justify-end gap-2 border-t border-border px-4 py-2.5">
              {job && job.done > 0 && jobId && (
                <button type="button" className={BTN_PRIMARY} onClick={() => triggerDownload(converterDownloadUrl(jobId))}>
                  <FileDown className="h-3.5 w-3.5" />
                  打包下载 ZIP
                </button>
              )}
              <button type="button" className={job && job.done > 0 ? BTN : BTN_PRIMARY} onClick={closeAll}>
                关闭
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function JobRow({ item, onPick }: { item: ConverterJobItem; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="flex w-full items-start gap-2.5 border-b border-border px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
    >
      <span
        className={cn(
          'mt-[2px] flex-none rounded-[6px] border px-1.5 py-[1px] text-[10px] font-semibold whitespace-nowrap',
          badgeOf(item.status),
        )}
      >
        {STATUS_LABEL[item.status] ?? item.status}
      </span>
      <span className="min-w-0 flex-1">
        <span className="text-[12px] leading-snug font-medium text-foreground">
          {item.total} 个文件 · 成功 {item.done}
          {item.failed > 0 ? ` · 失败 ${item.failed}` : ''}
        </span>
        <span className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <span>{format(new Date(item.createdAt), 'MM-dd HH:mm')}</span>
          {item.hasZip && (
            <>
              <span>·</span>
              <span>可下载</span>
            </>
          )}
        </span>
      </span>
    </button>
  )
}
