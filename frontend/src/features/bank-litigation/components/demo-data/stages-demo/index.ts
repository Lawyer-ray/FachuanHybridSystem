/**
 * 演示数据 · G. 单案诉讼线 · 六阶段（目录入口）
 *
 * 这条线讲的是「一个案子怎么从一叠扫描件走到法院立案」：
 *   ① 收案 → ② 读懂 → ③ 缺件 → ④ 文书 → ⑤ 回扫 → ⑥ 校验
 * 每个阶段的数据都围绕**同一个案件**（谭某某金融借款），不是统计报表。
 * 与 x1/x2/x3 三个下钻层模块共用同一批材料口径。
 *
 * ═══ 为什么按阶段拆成目录 ═══
 * 六阶段共 19 组数据、38 个导出，挤在一个文件里既过 350 行软红线，
 * 想改某一阶段的表也要在几百行里翻找。按阶段一文件后，真实功能上线时
 * 可以逐阶段删模块（本文件对应的 re-export 行一并删掉），使用方仍然
 * `from '../demo-data'`，不需要关心某个常量落在哪个文件。
 */

// ① 收案
export { DEMO_INTAKE_EVENTS, DEMO_INTAKE_SEGMENTS, DEMO_INTAKE_SOURCES } from './intake'
export type { IntakeEventRow, IntakeSegmentRow, SourceFileRow } from './intake'

// ② 读懂
export { DEMO_UNDERSTAND_DOCS, DEMO_UNDERSTAND_FIELDS, DEMO_UNDERSTAND_ISSUES } from './understand'
export type { UnderstandDocRow, UnderstandFieldRow, UnderstandIssueRow } from './understand'

// ③ 缺件
export { DEMO_GAP_NOTICES, DEMO_GAP_RECEIVED, DEMO_GAP_TEMPLATES } from './gap'
export type { GapNoticeRow, GapReceivedRow, GapTemplateRow } from './gap'

// ④ 文书
export { DEMO_CONFLICT_HITS, DEMO_CONTRACT_GEN, DEMO_CONTRACT_TERMS, DEMO_CONTRACT_TEMPLATES } from './contract'
export type { ConflictHitRow, ContractGenRow, ContractTermRow, ContractTemplateRow } from './contract'

// ⑤ 回扫
export { DEMO_RETURNED_DIFF, DEMO_RETURNED_MAILS, DEMO_SCAN_BATCHES } from './returned'
export type { ReturnedDiffRow, ReturnedMailRow, ScanBatchRow } from './returned'

// ⑥ 校验
export { DEMO_FILING_CHECKS, DEMO_FILING_FIXES, DEMO_SIGN_CHECKS } from './filing'
export type { FilingCheckRow, FilingFixRow, SignCheckRow } from './filing'
