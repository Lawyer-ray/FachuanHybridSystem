import { useEffect, useRef, useState } from 'react'
import { FileDown, Trash2 } from 'lucide-react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { toast } from 'sonner'

import {
  convertHistoryKeys,
  convertRecordDownloadUrl,
  deleteConvertRecord,
  listConvertRecords,
  triggerDownload,
  type ConvertRecordItem,
} from '../../../api'
import { cn } from '@/lib/utils'
import { errMessage } from '@/lib/errors'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { badgeOf } from './badges'
import { HistoryError } from './HistoryError'
import { HistoryHeader, HistoryPager } from './HistoryParts'

const STATUS_LABEL: Record<string, string> = { success: '成功', failed: '失败' }

const GROUPS = [
  { value: '', label: '全部' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
] as const

const ROW_BTN =
  'flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'

/** 行操作：下载（成功）+ 删除（两段确认，3.5 秒内再点执行） */
function Row({ item, onDeleted }: { item: ConvertRecordItem; onDeleted: () => void }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  // armed 复位定时器存 ref：行删除 / 翻页 / 关弹窗卸载时清掉，不对已卸载组件 setState
  const armTimer = useRef<number>(0)

  useEffect(() => () => window.clearTimeout(armTimer.current), [])

  const remove = async () => {
    if (!armed) {
      setArmed(true)
      armTimer.current = window.setTimeout(() => setArmed(false), 3500)
      return
    }
    setBusy(true)
    try {
      await deleteConvertRecord(item.id)
      toast.success('已删除该条转换记录')
      onDeleted()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败，请稍后重试')
    } finally {
      setBusy(false)
      setArmed(false)
      // 删除已执行，pending 的复位定时器不再需要
      window.clearTimeout(armTimer.current)
    }
  }

  return (
    <div className="flex items-start gap-2.5 border-b border-border px-4 py-2.5 last:border-b-0">
      <span
        className={cn(
          'mt-[2px] flex-none rounded-[6px] border px-1.5 py-[1px] text-[10px] font-semibold whitespace-nowrap',
          badgeOf(item.status),
        )}
      >
        {STATUS_LABEL[item.status] ?? item.status}
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-1 text-[12px] leading-snug font-medium text-foreground" title={item.original_name}>
          {item.original_name}
        </span>
        <span className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          {/* created_at 生成物为可选（null 兜底不渲染），避免 new Date(undefined) 得 Invalid Date */}
          {item.created_at && <span>{format(new Date(item.created_at), 'MM-dd HH:mm')}</span>}
          {item.mbid_name && (
            <>
              <span>·</span>
              <span className="truncate">{item.mbid_name}</span>
            </>
          )}
        </span>
        {item.status === 'failed' && item.error_message && (
          <span className="mt-0.5 line-clamp-1 text-[10.5px] text-status-red" title={item.error_message}>
            {item.error_message}
          </span>
        )}
      </span>
      <span className="mt-[2px] flex flex-none items-center gap-1.5">
        {item.has_file && (
          <button type="button" className={ROW_BTN} onClick={() => triggerDownload(convertRecordDownloadUrl(item.id))}>
            <FileDown className="h-3 w-3" />
            下载
          </button>
        )}
        <button
          type="button"
          className={cn(
            ROW_BTN,
            'hover:border-status-red/50 hover:text-status-red',
            armed && 'border-status-red/60 text-status-red',
          )}
          disabled={busy}
          title="删除该条记录（含产物文件）"
          onClick={() => void remove()}
        >
          <Trash2 className="h-3 w-3" />
          {armed ? '确认？' : '删除'}
        </button>
      </span>
    </div>
  )
}

/** 要素式转换历史弹窗：每次转换的产物已落库，可直接重下 / 删除 */
export function ConvertHistoryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [group, setGroup] = useState('')
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: convertHistoryKeys.page(group, page),
    queryFn: () => listConvertRecords(group || undefined, page),
    enabled: open,
    staleTime: 10_000,
    // 翻页/切组时保留上一屏数据，避免列表闪「正在加载…」、弹窗高度跳动
    placeholderData: keepPreviousData,
  })

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / 20))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
        <HistoryHeader title="要素式转换历史" count={count}>
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
          {isError ? (
            <HistoryError error={errMessage(error, '历史记录加载失败')} onRetry={() => void refetch()} />
          ) : isLoading ? (
            <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">正在加载…</div>
          ) : items.length === 0 ? (
            <div className="px-4 py-8 text-center text-[12px] text-muted-foreground">
              这个筛选下没有记录（历史自本功能上线起保留）
            </div>
          ) : (
            items.map((it) => (
              <Row key={it.id} item={it} onDeleted={() => void queryClient.invalidateQueries({ queryKey: convertHistoryKeys.all })} />
            ))
          )}
        </div>

        <HistoryPager page={page} totalPages={totalPages} onChange={setPage} />
      </DialogContent>
    </Dialog>
  )
}
