/**
 * ③ 缺件 —— 抽屉里的客户往来时间线（一条缺件的完整沟通过程）。
 *
 * 补件是来回拉扯的过程，所以按时间正序逐条列出：谁、什么时候、通过什么渠道、说了什么。
 * 系统识别的节点标绿、客户回传的节点标蓝，其余走中性色。
 */
import { Bell, CheckSquare, Mail, MessageSquare, Smartphone, Upload, Users } from 'lucide-react'

import { DEMO_X2_GAP_TIMELINE, type GapTimelineKind } from '../../demo-data'
import { InsetBlock } from '../../ui'
import { cn } from '@/lib/utils'

/** 时间线里每类事件的图标（渠道图标） */
const TIMELINE_ICON: Record<GapTimelineKind, typeof Mail> = {
  system: Bell,
  sms: Smartphone,
  mail: Mail,
  wechat: MessageSquare,
  customer: Upload,
  recognize: CheckSquare,
}

/** 客户往来时间线 */
export function GapTimelineBlock({ item }: { item: string }) {
  const timeline = DEMO_X2_GAP_TIMELINE.filter((t) => t.item === item)

  return (
    <InsetBlock>
      <div className="flex items-center gap-1.5">
        <Users className="size-3 text-muted-foreground" />
        <span className="text-[10px] text-muted-foreground">客户往来时间线（{timeline.length} 条）</span>
      </div>
      {timeline.length === 0 ? (
        <p className="mt-1.5 text-[10.5px] text-muted-foreground">还没有往来记录</p>
      ) : (
        <ol className="mt-2 flex flex-col">
          {timeline.map((t, i) => {
            const Icon = TIMELINE_ICON[t.kind]
            const last = i === timeline.length - 1
            return (
              <li key={`${t.at}-${t.title}`} className="flex gap-2.5">
                <div className="flex flex-none flex-col items-center">
                  <span
                    className={cn(
                      'grid size-[18px] place-items-center rounded-full border',
                      t.kind === 'recognize'
                        ? 'border-status-green/40 bg-status-green-bg text-status-green'
                        : t.kind === 'customer'
                          ? 'border-status-blue/40 bg-status-blue-bg text-status-blue'
                          : 'border-border bg-secondary text-muted-foreground',
                    )}
                  >
                    <Icon className="size-2.5" />
                  </span>
                  <span className={cn('mt-1 w-px flex-1 bg-border-light', last && 'hidden')} />
                </div>
                <div className="min-w-0 pb-3">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-[11.5px] font-medium">{t.title}</span>
                    <span className="text-[10px] tabular-nums text-muted-foreground">{t.at}</span>
                    <span className="rounded-[4px] border border-border-light bg-card px-1 text-[9.5px] text-muted-foreground">
                      {t.channel}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">{t.detail}</div>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </InsetBlock>
  )
}
