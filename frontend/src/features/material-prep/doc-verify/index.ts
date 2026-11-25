/**
 * 回传件内容核对（客户把起诉状等签字件传回来 → 与出站基线比对正文 → 律师裁决）。
 *
 * 这是 `material-prep` 域内的一个子域（与 `components/reader/` 同级），不新建 feature：
 * 业务上它就是「材料归案之后客户寄回来的那一份」，后端也挂在同一批案件材料上。
 *
 * 出口：清单组件、勾选框、四个接口函数、以及 schema 派生的类型。
 */
export { PendingRuns } from './PendingRuns'
export { PolicyToggle } from './PolicyToggle'
export {
  decideBatch,
  decideRun,
  getPolicy,
  listCaseRuns,
  listPending,
  listUnverified,
  putPolicy,
  runFromMaterial,
} from './api'
export type {
  DecisionAction,
  DecisionIn,
  DecisionOut,
  FindingOut,
  PolicyIn,
  PolicyItemOut,
  PolicyOut,
  VerifyRunOut,
} from './api'
