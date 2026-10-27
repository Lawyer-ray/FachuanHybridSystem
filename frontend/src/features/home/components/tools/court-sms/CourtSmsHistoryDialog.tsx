import { useState } from 'react'
import { ChevronRight, FileText, History } from 'lucide-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'

import { courtSmsHistoryKeys, listCourtSms, type CourtSmsGroup, type CourtSmsListItem } from '../../../api'
import { cn } from '@/lib/utils'
import { errMessage } from '@/lib/errors'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { HistoryError } from '../history/HistoryError'
import { HistoryPager } from '../history/HistoryParts'
import { SMS_STATUS_LABEL } from './stages'

/** 状态 → 色档（需处理类显眼，进行中蓝，完成绿）。
 *  基础映射与 history/badges.ts 一致（completed 绿 / failed 红），只对本域特有的两个
 *  状态做**局部覆盖**：pending_manual（待人工处理 → 黄）、download_failed（下载失败 → 红）。
 *  不直接复用 history 的 badgeOf：它没这两个键，会落到蓝色兜底，视觉口径就变了。 */
const STATUS_TONE_OVERRIDE: Record<string, Tone> = {
  pending_manual: 'yellow',
  download_failed: 'red',
}
const STATUS_TONE: Record<string, Tone> = { completed: 'green', failed: 'red', ...STATUS_TONE_OVERRIDE }
const toneOf = (status: string): Tone => STATUS_TONE[status] ?? 'blue'

const GROUPS: { value: CourtSmsGroup; label: string }[] = [
  { value: 'needs_action', label: '需处理' },
  { value: 'completed', label: '已完成' },
  { value: 'all', label: '全部' },
]

const PAGE_SIZE = 20

function Row({ item, onPick }: { item: CourtSmsListItem; onPick: (id: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onPick(item.id)}
      className="flex w-full items-start gap-2.5 border-b border-border px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-secondary/60"
    >
      <StatusBadge tone={toneOf(item.status)} className="mt-[2px]">
        {SMS_STATUS_LABEL[item.status] ?? item.status}
      </StatusBadge>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-[12px] leading-snug text-foreground">{item.content}</span>
        <span className="mt-1 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <span>{format(new Date(item.received_at), 'MM-dd HH:mm')}</span>
          {item.case_name && (
            <>
              <span>·</span>
              <span className="truncate">{item.case_name}</span>
            </>
          )}
          {item.has_documents && (
            <>
              <span>·</span>
              <FileText className="h-3 w-3 flex-none text-status-blue" />
            </>
          )}
        </span>
      </span>
      <ChevronRight className="mt-1 h-4 w-4 flex-none text-muted-foreground" />
    </button>
  )
}

/**
 * 法院短信历史弹窗：分页浏览过往记录，按状态组筛选；
 * 点某条交给 onPick —— 由卡片把处理弹窗打开到该记录上（人工分配/重试/下载/复制都可用），
 * 这样不必再做独立的法院短信页面。
 */
export function CourtSmsHistoryDialog({
  open,
  onOpenChange,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (smsId: number) => void
}) {
  const [group, setGroup] = useState<CourtSmsGroup>('needs_action')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: courtSmsHistoryKeys.page(group, page),
    queryFn: () => listCourtSms(group, page),
    enabled: open,
    staleTime: 10_000,
    // 翻页/切组时保留上一屏数据，避免列表闪「正在加载…」、弹窗高度跳动
    placeholderData: keepPreviousData,
  })

  const items = data?.items ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  const switchGroup = (g: CourtSmsGroup) => {
    setGroup(g)
    setPage(1)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[46%] flex max-h-[80vh] flex-col gap-0 p-0 sm:max-w-[560px]">
        <div className="flex flex-none items-center gap-2.5 border-b border-border px-4 py-3 pr-10">
          <History className="h-4 w-4 flex-none text-muted-foreground" />
          <b className="text-[13.5px] font-semibold">历史短信</b>
          <span className="text-[11px] text-muted-foreground">{count} 条</span>
          <span className="flex-1" />
          <div className="flex items-center gap-1">
            {GROUPS.map((g) => (
              <button
                key={g.value}
                type="button"
                onClick={() => switchGroup(g.value)}
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
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {isError ? (
            <HistoryError error={errMessage(error, '历史短信加载失败')} onRetry={() => void refetch()} />
          ) : isLoading ? (
            <LoadingBlock text="正在加载…" />
          ) : items.length === 0 ? (
            <EmptyBlock>这个筛选下没有记录</EmptyBlock>
          ) : (
            items.map((it) => <Row key={it.id} item={it} onPick={onPick} />)
          )}
        </div>

        {/* 分页底栏与其余三张工具卡的历史弹窗同款，复用 HistoryPager */}
        <HistoryPager page={page} totalPages={totalPages} onChange={setPage} />
      </DialogContent>
    </Dialog>
  )
}
