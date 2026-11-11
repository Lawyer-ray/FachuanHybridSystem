/**
 * ③ 缺件 —— 客户补回来的材料（系统自动识别并归入对应槽位）。
 *
 * 只读展示：补回来的每一项带文件名、页数、收到时间与识别说明。
 */
import { CheckCircle2 } from 'lucide-react'

import { DEMO_GAP_RECEIVED } from '../../demo-data'
import { Pill, SectionTitle, WorkCard } from '../../ui'

/** 客户补回来的材料 */
export function GapReceivedCard() {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle title="客户补回来的材料" hint="系统自动识别并归入对应槽位" className="w-full" />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_GAP_RECEIVED.map((r) => (
          <li key={r.item} className="flex items-start gap-3 px-5 py-3">
            <CheckCircle2 className="mt-[3px] size-4 flex-none text-status-green" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[12px] font-medium">{r.item}</span>
                <Pill tone="green">已补齐</Pill>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                <span>{r.fileName}</span>
                <span className="text-border">·</span>
                <span>{r.pages} 页</span>
                <span className="text-border">·</span>
                <span>{r.receivedAt}</span>
              </div>
              <div className="mt-0.5 text-[10.5px] text-status-green">{r.note}</div>
            </div>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}
