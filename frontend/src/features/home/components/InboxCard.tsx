import { useState } from 'react'
import { ChevronDown, Landmark, Mail, Paperclip } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { HOME_INBOX_KEY, listInbox } from '../api'
import type { InboxItem } from '../types'
import { PANEL } from '../ui'
import { InboxMessageContent } from '@/features/material-prep'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { CardHead } from '@/components/shared/CardHead'
import { inboxPath } from '@/app/paths'

interface InboxProps {
  /** 点击行：材料包/已转过的直接进阅读器（由页面决定怎么走） */
  onOpen: (item: InboxItem) => void
  /** 就地展开里的「转材料包并打开」走同一条路 */
  onOpenPack: (packId: number) => void
}

/**
 * 右栏「收件箱」：最近流入的消息（法院短信 / 一张网通知书 / 邮件 / 材料包）。
 *
 * 这里刻意**不**叫「待处理」、也不给每条配一排动作按钮。原因（实测数据）：
 * 收件箱 338 条里 court_inbox 121 条、imap 215 条、manual_upload 仅 2 条；
 * 而 status（todo/done/filed）只对 manual_upload 有意义——它是写在
 * draft_state 里的、由材料预处理页维护。也就是说其余 336 条的 status 恒为
 * todo，「待处理 N 条」这个计数没有信息量。
 *
 * **点击行为（2026-10 修正）**：点一行就地展开读正文/附件，**不再跳**到
 * 收件箱列表。此前非材料包类一律 navigate 到 /material-prep，用户以为在看
 * 详情，落地却是一屏 300+ 条同质消息、还得靠标题文本自己再找一遍——而法院
 * 送达里五条标题都叫「Attached Image」时根本无法肉眼区分。真正要横向浏览时
 * 走右上「查看全部」。只有材料包（或已转过的消息）才直接进阅读器。
 */
export function InboxCard({ onOpen, onOpenPack }: InboxProps) {
  const { data = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: HOME_INBOX_KEY,
    queryFn: () => listInbox(6),
    staleTime: 30_000,
  })

  // 手风琴：同时只展开一条（侧栏空间窄，多条展开会把下面几行顶出视口）
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead
        title="收件箱"
        count={isError ? '' : data.length ? `${data.length} 条` : ''}
        moreHref={inboxPath()}
      />
      <div className="px-2.5 pt-1.5 pb-2.5">
        {isError && (
          /* 失败与空收件箱必须分得开：否则服务端故障会被读成「没有新消息」 */
          <div className="px-2 py-6 text-center text-[12.5px] text-destructive">
            {errMessage(error, '收件箱加载失败')}
            <button
              type="button"
              className="ml-1.5 cursor-pointer underline underline-offset-3"
              onClick={() => void refetch()}
            >
              重试
            </button>
          </div>
        )}
        {!isError && isLoading && <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>}
        {!isError && !isLoading && data.length === 0 && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">收件箱是空的</div>
        )}
        {data.map((x) => {
          const expanded = expandedId === x.id
          return (
            <div key={x.id}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => {
                  // 材料包 / 已转过的消息：进去就是要看阅读器，展开再点一次是多余一层
                  if (x.packId != null) {
                    onOpen(x)
                    return
                  }
                  setExpandedId(expanded ? null : x.id)
                }}
                className={cn(
                  'flex w-full items-center gap-[11px] rounded-[10px] px-2 py-[10px] text-left transition-colors hover:bg-secondary/50',
                  expanded && 'bg-secondary/40',
                )}
              >
                <div
                  className={cn(
                    'flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border',
                    x.hot
                      ? 'border-status-red/30 bg-status-red-bg text-status-red'
                      : 'border-border bg-secondary text-secondary-foreground',
                  )}
                >
                  <KindIcon kind={x.kind} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] leading-[1.4] font-semibold">{x.title}</div>
                  <div className="mt-[1px] truncate text-[10.5px] text-muted-foreground">
                    {x.sourceLabel} · {x.who}
                  </div>
                </div>
                <span className="flex-none text-[10.5px] whitespace-nowrap text-muted-foreground">{x.at}</span>
                {/* 可展开的才给指示器：材料包可直接进阅读器，画个三角反而暗示有东西展开却打不开 */}
                {x.packId == null && (
                  <ChevronDown
                    aria-hidden
                    className={cn(
                      'h-3.5 w-3.5 flex-none text-muted-foreground transition-transform',
                      expanded && 'rotate-180',
                    )}
                  />
                )}
              </button>
              {expanded && (
                <div className="mb-1 ml-[43px] mr-2 rounded-[10px] border border-border bg-card px-3 py-2.5">
                  {/* 消息行就是 InboxMessageOut，与收件箱页抽屉同形，直接喂给它 */}
                  <InboxMessageContent row={x.row} onConverted={onOpenPack} onOpenPack={onOpenPack} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function KindIcon({ kind }: { kind: InboxItem['kind'] }) {
  if (kind === 'sms') return <Landmark className="h-4 w-4" />
  if (kind === 'mail') return <Mail className="h-4 w-4" />
  return <Paperclip className="h-4 w-4" />
}
