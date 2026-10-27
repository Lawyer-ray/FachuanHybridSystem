/**
 * 争议解决详情页的派生数据总出口（barrel）。
 *
 * 纯领域逻辑按关注点拆在 `detail/` 下：改右栏（rail-domain）不会再牵动案件节
 * 与程序链；消费组件仍统一从本文件 import，拆分对调用方零改动。
 *
 * 这里逐个显式列出 re-export 而**不用 `export *`**：`export *` 会把内部模块的
 * 全部导出面摊平，新增/删除一个内部符号都悄悄变成对外 API 变更；逐个列出时
 * 出口面一眼可查（lazy 分包行为两者一致，工作台详情页仍走 index.ts 的 import()）。
 */

export type { ChainStep, StagePlan, StepState } from './detail/chain-domain'
export {
  STAGE_ORDER,
  ambiguousStages,
  buildStagePlan,
  chainSteps,
  chainSummary,
  nextStage,
  orderChain,
  planCases,
} from './detail/chain-domain'

export type { MetaPart, TimelineEntry } from './detail/case-section-domain'
export { caseMetaParts, legalStatusGroups, timelineEntries } from './detail/case-section-domain'

export type { Deadline } from './detail/rail-domain'
export {
  buildDeadlines,
  contactGroups,
  dueLabel,
  feeStats,
  moneyRows,
  railFacts,
  railParties,
} from './detail/rail-domain'

export { crumbName, headerMetaParts } from './detail/header-domain'

export type { TextSegment } from './detail/filename-text'
export { shortDocName, splitLinkText, stripEntryParens } from './detail/filename-text'
