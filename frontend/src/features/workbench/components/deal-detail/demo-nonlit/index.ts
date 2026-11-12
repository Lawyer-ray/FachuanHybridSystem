/**
 * 非诉线 · 演示数据桶出口（**仅用于录屏演示**，不参与真实业务）
 *
 * 原 `demo-nonlit.ts` 是单文件 1583 行 / 54 个导出，越过 450 行硬红线。
 * 它头部已声明覆盖三个非诉场景，这里就按那条边界拆成三个场景，
 * 每个场景可独立删除（真实数据落地时按场景逐个退场，不必动其他场景）。
 *
 *   · 专项服务（关厂清盘）  → `nl1-special.ts`（阶段/模板）
 *                            + `nl1-special-evidence.ts`（变更/版本/风险/确认/甘特）
 *   · 跨境合同审查（泰国）  → `nl2-crossborder.ts`（审查结论）
 *                            + `nl2-crossborder-doc.ts`（双语正文/法条原文/对方意见）
 *   · 常年法律顾问          → `nl3-advisor.ts`（服务事项表/统计）
 *                            + `nl3-service-items.ts`（16 条明细）
 *                            + `nl3-advisor-stats.ts`（工时/满意度/风险）
 *   · 跨场景共用类型        → `types.ts`
 *
 * **本文件导出的符号集合与名字必须与拆分前完全一致**：33 个引用方直接
 * `from '.../demo-nonlit'` 取值，改名只会砸到引用方。
 * `verbatimModuleSyntax` 已开，类型必须走 `export type`，否则运行时 import 会被保留。
 */

export type { DemoDeliverable } from './types'

// A. 专项服务（关厂清盘）
export { DEMO_DRAFT_SUGGESTIONS, DEMO_NONLIT_PHASES, DEMO_PHASE_TEMPLATES } from './nl1-special'
export type { DemoDraftSuggestion, DemoPhase, DemoPhaseTemplate } from './nl1-special'
export {
  DEMO_NL1_CHANGE_LOGS,
  DEMO_NL1_CLIENT_CONFIRMS,
  DEMO_NL1_DOC_HISTORY,
  DEMO_NL1_GANTT,
  DEMO_NL1_GATE_RULES,
  DEMO_NL1_RISKS,
} from './nl1-special-evidence'
export type {
  DemoNl1ChangeLog,
  DemoNl1ClientConfirm,
  DemoNl1DocHistory,
  DemoNl1DocVersion,
  DemoNl1GanttRow,
  DemoNl1GateRule,
  DemoNl1Risk,
} from './nl1-special-evidence'

// B. 跨境合同审查（泰国工厂租赁）· 审查结论
export { DEMO_LAW_GATES, DEMO_TH_CONTRACT_REVISIONS, DEMO_VERIFY_LOG } from './nl2-crossborder'
export type { DemoContractRevision, DemoLawGate, DemoVerifyLogRow } from './nl2-crossborder'
// B. 跨境合同审查（泰国工厂租赁）· 双语文档视图的补充数据
export {
  DEMO_NL2_CONTRACT,
  DEMO_NL2_COUNTER_OPINIONS,
  DEMO_NL2_FILTERS,
  DEMO_NL2_LAW_EXCERPTS,
  DEMO_NL2_REVIEW_PROGRESS,
  DEMO_REVISION_BY_ID,
} from './nl2-crossborder-doc'
export type {
  DemoNl2Clause,
  DemoNl2ClauseSegment,
  DemoNl2ClauseSentence,
  DemoNl2CounterOpinion,
  DemoNl2Filter,
  DemoNl2LawExcerpt,
  DemoNl2ReviewProgress,
} from './nl2-crossborder-doc'

// C. 常年法律顾问
export { DEMO_SERVICE_ITEMS, DEMO_SERVICE_STATS } from './nl3-advisor'
export type { DemoServiceItem } from './nl3-advisor'
export { DEMO_NL3_SERVICE_ITEMS } from './nl3-service-items'
export type { DemoNl3Effort, DemoNl3ServiceItem, DemoNl3ServiceKind } from './nl3-service-items'
export {
  DEMO_NL3_MONTHLY_HOURS,
  DEMO_NL3_QUOTA_POLICY,
  DEMO_NL3_RISKS,
  DEMO_NL3_SATISFACTION,
  DEMO_NL3_SERVICE_STATS,
} from './nl3-advisor-stats'
export type {
  DemoNl3MonthHours,
  DemoNl3Risk,
  DemoNl3Satisfaction,
} from './nl3-advisor-stats'
