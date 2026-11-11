/**
 * 回扫 —— 「回扫带来的变化」。
 *
 * 材料补齐后各阶段指标怎么动：前值 → 后值 → 差值。
 * 纯展示，数据来自演示常量。
 */
import { DEMO_RETURNED_DIFF } from '../../demo-data'
import { Pill, SectionTitle, WorkCard } from '../../ui'

/** 回扫前后指标变化表 */
export function ReturnedDiffTable() {
  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle title="回扫带来的变化" hint="材料补齐后各指标怎么动" className="w-full" />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_RETURNED_DIFF.map((r) => (
          <li key={r.stage} className="flex items-center gap-3 px-5 py-2.5">
            <span className="w-[84px] flex-none text-[11.5px] text-muted-foreground">{r.stage}</span>
            <span className="w-[92px] flex-none text-[12px]">{r.before}</span>
            <span className="flex-none text-[10px] text-border">→</span>
            <span className="w-[92px] flex-none text-[12px] font-medium">{r.after}</span>
            <Pill tone={r.delta.startsWith('+') ? 'green' : 'blue'}>{r.delta}</Pill>
          </li>
        ))}
      </ul>
    </WorkCard>
  )
}
