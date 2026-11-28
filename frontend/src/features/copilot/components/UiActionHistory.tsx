/**
 * AI 操作历史：把 UI 动作审计台账摆到律师眼前（只读）。
 *
 * ## 为什么要有这张表
 *
 * 审批卡只在「要执行」的那一刻存在；执行完，AI 动过什么就只剩服务端台账。
 * 律师事后问「上周那个删除是不是我批的」「AI 说改好了，库里到底改了没」，
 * 需要一个能自己查的地方。面板把事实摊开：动作、结局、核实结论、谁批的、时间。
 *
 * ## 为什么只读、不做筛选
 *
 * 台账的价值是「可核对」，不是「可运营」。分页 / 筛选 / 删除 / 导出都等真实
 * 需求出现再做；现在默认最近 50 条，足够回答「刚才 AI 到底动了什么」。
 *
 * ## 为什么由宿主决定挂不挂载
 *
 * 没打开就不该发请求（也就不用给 header 的其余单测准备 QueryClient）。宿主
 * `CopilotHeader` 只在点开「历史」之后渲染本组件，打开态只是 header 的本地 state
 * ——台账按律师查、与当前会话无关，放进 store 没有第二个读者。
 */

import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

import { fetchUiActionHistory } from '../api'
import { toUiActionHistoryRow, type UiActionHistoryTone, type UiActionVerifyKind } from '../domain/ui-action-history'

/** 默认拉最近 50 条（与后端默认值一致；本面板不做分页） */
const HISTORY_LIMIT = 50

/** 结局徽标色调；文字（`outcomeLabel`）始终在，颜色只是第二眼 */
const TONE_CLASS: Record<UiActionHistoryTone, string> = {
  ok: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  error: 'bg-destructive/10 text-destructive',
  warn: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  muted: 'bg-secondary text-muted-foreground',
}

/** 核实不一致必须标红：这是整张面板最重要的一种状态 */
const VERIFY_CLASS: Record<UiActionVerifyKind, string> = {
  verified: 'text-emerald-700 dark:text-emerald-400',
  mismatch: 'text-destructive',
  unverified: 'text-muted-foreground',
}

export interface UiActionHistoryProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function UiActionHistory({ open, onOpenChange }: UiActionHistoryProps) {
  const query = useQuery({
    queryKey: ['copilot', 'ui-action-history', HISTORY_LIMIT],
    queryFn: () => fetchUiActionHistory(HISTORY_LIMIT),
    enabled: open,
    // 每次打开都重拉：这张表是用来核对「刚才 AI 动了什么」的，全局 15s 的
    // staleTime 会让刚发生的动作在重开面板时看不到（缓存里还是上一份）。
    staleTime: 0,
  })
  const rows = (query.data ?? []).map(toUiActionHistoryRow)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] flex-col gap-3 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>AI 操作历史</DialogTitle>
          <DialogDescription>只有需要审批的界面动作才有记录；只列你自己的，最近的在前。</DialogDescription>
        </DialogHeader>

        {query.isError ? (
          <div className="flex flex-col items-start gap-2 py-2">
            <p className="text-[12.5px] text-muted-foreground">操作历史加载失败，请稍后重试。</p>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              重试
            </Button>
          </div>
        ) : query.isPending ? (
          <p className="py-2 text-[12.5px] text-muted-foreground">正在加载…</p>
        ) : rows.length === 0 ? (
          <p className="py-2 text-[12.5px] text-muted-foreground">还没有 AI 操作记录</p>
        ) : (
          <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1" aria-label="AI 操作记录">
            {rows.map((row, index) => (
              <li
                key={`${row.action}-${row.createdAt}-${index}`}
                className="rounded-[10px] border border-border px-3 py-2"
              >
                <div className="flex items-center gap-1.5">
                  <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">{row.title}</span>
                  <span
                    className={cn(
                      'flex-none rounded-[4px] px-1.5 py-px text-[10.5px] font-medium',
                      TONE_CLASS[row.outcomeTone],
                    )}
                  >
                    {row.outcomeLabel}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-muted-foreground">
                  {row.at && <time dateTime={row.createdAt}>{row.at}</time>}
                  {row.approvedByLabel && <span>{row.approvedByLabel}</span>}
                  {row.verify && <span className={VERIFY_CLASS[row.verify.kind]}>{row.verify.label}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}
