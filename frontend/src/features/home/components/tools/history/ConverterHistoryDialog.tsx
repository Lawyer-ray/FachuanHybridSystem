import { useState } from 'react'
import { CheckCircle2, ChevronRight, FileDown, History, XCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'

import {
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
import { FlowNotice, TaskFlowDialog } from '../dialog/TaskFlowDialog'
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

/** DOC 转 DOCX 历史弹窗：列出过往任务，点开某单重新下载（单件 / ZIP） */
export function ConverterHistoryDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [page, setPage] = useState(1)
  const [pickedId, setPickedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['doc-converter-history', page],
    queryFn: () => listConverterJobs(page),
    enabled: open,
    staleTime: 10_000,
  })

  const { data: job } = useQuery({
    queryKey: ['doc-converter-job', pickedId],
    queryFn: () => getConverterJob(pickedId!),
    enabled: pickedId !== null,
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / 20))
  const okItems = (job?.items ?? []).filter((it) => it.ok)
  const detailOpen = pickedId !== null

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
          <HistoryHeader title="DOC 转 DOCX 历史" count={count} />

          <div className="min-h-0 flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">正在加载…</div>
            ) : items.length === 0 ? (
              <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">还没有转换任务</div>
            ) : (
              items.map((it) => (
                <JobRow key={it.id} item={it} onPick={() => setPickedId(it.id)} />
              ))
            )}
          </div>

          <HistoryPager page={page} totalPages={totalPages} onChange={setPage} />
        </DialogContent>
      </Dialog>

      <TaskFlowDialog
        open={detailOpen}
        onOpenChange={(o) => {
          if (!o) setPickedId(null)
        }}
        icon={<History className="h-5 w-5" />}
        title="DOC 转 DOCX 历史"
        tone={job ? (job.done > 0 ? 'success' : 'error') : 'running'}
        headline={job ? (job.done > 0 ? '转换记录' : '该任务无成功产物') : '正在载入记录…'}
        subline={job ? `共 ${job.total} 件 · 成功 ${job.done}${job.failed > 0 ? ` · 失败 ${job.failed}` : ''}` : undefined}
        wide
        footer={
          <>
            {detailOpen && job && job.done > 0 && (
              <button type="button" className={BTN_PRIMARY} onClick={() => triggerDownload(converterDownloadUrl(detailOpen ? pickedId! : ''))}>
                <FileDown className="h-3.5 w-3.5" />
                打包下载 ZIP
              </button>
            )}
            <button type="button" className={job && job.done > 0 ? BTN : BTN_PRIMARY} onClick={() => setPickedId(null)}>
              关闭
            </button>
          </>
        }
      >
        {job && job.done > 0 && (
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
                <button
                  type="button"
                  className={ROW_BTN}
                  onClick={() => triggerDownload(converterItemDownloadUrl(pickedId!, it.id))}
                >
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
        )}
        {job && job.done === 0 && <FlowNotice kind="error">该任务没有转换成功的文件</FlowNotice>}
      </TaskFlowDialog>
    </>
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
      <ChevronRight className="mt-1 h-4 w-4 flex-none text-muted-foreground" />
    </button>
  )
}
