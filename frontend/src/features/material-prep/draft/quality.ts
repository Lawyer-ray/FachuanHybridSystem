/**
 * 识别质量提示的纯逻辑：页级质量统计 + 跨页不一致清单 + 段级复核信号。
 *
 * ## 为什么需要这一层
 *
 * 后端已经在 `summary` 里给出了「哪几页是图纸、哪几页几乎没字」以及「同一枚章被
 * 识别成了两种写法」，但字段全是自由字典、旧任务里根本没有。前端消费它的地方有三处
 * （左栏段行、右栏正文面板、全局清单），如果三处各自 `summary.page_quality as ...`
 * 强转，任何一处漏判空都会在「打开一个旧材料包」时白屏。
 *
 * 所以这里只做一件事：把不可信的 `unknown` 收窄成**明确的可选结构**，再给几组
 * 派生量（某段覆盖了哪些图形页、提示文案怎么写）。组件只读收窄后的结果。
 *
 * ## 拆成四块（互不相关的领域）
 * - `page-quality.ts`：页级质量收窄 + 段-页覆盖派生 + 证件待补录；
 * - `page-anomaly.ts`：页级识别风险（退化页 / 表格列数突变）收窄 + 段-页覆盖派生；
 * - `pairs.ts`：跨页不一致的收窄、判据种类与排序；
 * - `review-hint.ts`：段级复核信号 → 人话。
 *
 * 本文件只做出口，`draft/index.ts` 与单测继续从 `./quality` 引，import 路径不变。
 */
export {
  readPageQuality,
  qualityOf,
  graphicPagesOf,
  ocrFailedPagesOf,
  sparsePagesOf,
  docHintPagesOf,
  docTypeLabel,
  docTodosOf,
  qualityFlagLabel,
  pagesText,
} from './page-quality'
export type { DocHintPage, DocTodo } from './page-quality'
export {
  readPageAnomaly,
  degeneratePagesOf,
  columnAnomalyPagesOf,
  columnAnomaliesOf,
  columnAnomalyOf,
  riskPageKeysOf,
} from './page-anomaly'
export { readInconsistencies, inconsistencyKindOf, sortInconsistencies } from './pairs'
export type { InconsistencyKind } from './pairs'
export { reviewHintOf } from './review-hint'
export type { SegmentReviewHint } from './review-hint'
