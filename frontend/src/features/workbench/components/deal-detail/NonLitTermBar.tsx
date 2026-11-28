import type { ServiceItem } from './ServiceItemStream'
import type { PhaseNode } from './special-phase-tree'
import { flattenTree } from './special-phase-tree'
import { TermBar } from './TermBar'

/**
 * 非诉页的周期轴：两种工作脊椎的轴语义不同，放在同一处才能看出它们互斥。
 *
 * - 常法顾问：服务期 + **服务事项刻度**（回答「这一年哪几天在干活」）；
 * - 专项服务：项目周期 + **阶段里程碑**（回答「走到第几阶段」）。
 *
 * 判据是页面算好的 `isSpecial`（后端 case_type，不是本组件猜的）；合同没填
 * 服务期（from/to 缺一）时整条轴不渲染——没有起止日就画不出比例。
 */
export function NonLitTermBar({
  from,
  to,
  today,
  isSpecial,
  tree,
  serviceItems,
}: {
  from: string
  to: string
  /** 今天（yyyy-mm-dd）：与「今天」高亮共用同一口径，由页面算一次传入 */
  today: string
  isSpecial: boolean
  /** 专项阶段树：里程碑与「阶段 N / M」图例都从它派生 */
  tree: PhaseNode[]
  /** 常法服务事项：只有日期 + 标题上轴 */
  serviceItems: ServiceItem[]
}) {
  if (!from || !to) return null

  const phases = isSpecial ? flattenTree(tree) : []

  return (
    <div className="mb-[18px]">
      {isSpecial ? (
        <TermBar
          from={from}
          to={to}
          today={today}
          title="项目周期"
          milestones={phases
            .filter((x) => !!x.node.startDate)
            .map((x) => ({ date: x.node.startDate, title: x.node.name, state: phaseTone(x.node.state) }))}
          legend={
            phases.length > 0
              ? `阶段 ${phases.filter((x) => x.node.state === 'done').length} / ${phases.length}`
              : undefined
          }
        />
      ) : (
        <TermBar
          from={from}
          to={to}
          today={today}
          events={serviceItems.map((i) => ({ date: i.date, title: i.title }))}
        />
      )}
    </div>
  )
}

/** 阶段状态 → 周期轴刻度语义（done 对齐 term-timeline 的 ok） */
function phaseTone(state: PhaseNode['state']): 'ok' | 'doing' | 'todo' {
  if (state === 'done') return 'ok'
  return state === 'doing' ? 'doing' : 'todo'
}
