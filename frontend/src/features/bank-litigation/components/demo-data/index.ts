/**
 * 立案工作台 · 演示数据（**仅用于录屏/演示，不参与真实业务**）
 *
 * ═══ 这是演示数据的唯一入口（barrel） ═══
 * 数据实体按业务域拆在同目录下的 `*-demo.ts` 里，本文件只做统一再导出：
 * 使用方继续 `from '../demo-data'` / `from './demo-data'` 即可，不需要关心
 * 某个常量落在哪个模块。
 *
 * ═══ 为什么拆开 ═══
 * 这些数据是为「路演录屏」凑的画面填充物：整包分段的历史记录、OA 立案的
 * 执行日志、要素式转换的样例等。它们**不来自任何后端接口**，纯前端常量。
 * 按域拆开后，真实功能上线时逐域删模块即可（本文件对应的 re-export 行一并删掉），
 * 不需要在 7 个组件里到处找散落的假数据。
 *
 * ═══ 使用约定（硬性） ═══
 * 1. 只允许出现在**展示性**位置（表格行、时间线、统计数字），
 *    绝不能参与任何判断逻辑（`if (DEMO_xxx)` 这种用法禁止）。
 * 2. 所有名称/案号已脱敏：案号用「（20XX）粤0606民初XXXX号」，人名用「某某」。
 *    这是 pre-commit 的隐私闸门要求，也是演示材料该有的样子。
 * 3. 数值要与真实业务口径一致（金额千分位、页码区间连续、时间倒序），
 *    否则律师一眼看出是假的，演示反而减分。
 */

// 共享类型（被多个域共用，单独放 types.ts）
export {
  type AssignCandidate,
  type ClaimFilter,
  type GapSource,
  type GapTimelineEvent,
  type GapTimelineKind,
  type MailAttachment,
  type OASiteRow,
  type ScanMailboxConfig,
  type SplitHistoryRow,
  type X1DocLineKind,
  type X1PageBox,
  type X1PreviewPage,
} from './types'

// A. 整包分段（基础版）
export {
  DEMO_SPLIT_HISTORY,
  DEMO_SPLIT_TEMPLATE_TYPES,
} from './split-demo'

// B1. OA 立案
export {
  DEMO_OA_FIELD_MAPPING,
  DEMO_OA_FILING_LOG,
  DEMO_OA_FAILURE_CAUSES,
  DEMO_OA_HISTORY,
  DEMO_OA_SITES,
  type OAFailureCause,
  type OAFieldMappingRow,
  type OAFilingHistoryRow,
  type OAFilingLogRow,
} from './oa-filing-demo'

// B2. OA 盖章
export {
  DEMO_OA_SEALS,
  DEMO_OA_SEAL_RULES,
  DEMO_STAMP_BATCHES,
  DEMO_STAMP_FAILURES,
  DEMO_STAMP_HISTORY,
  DEMO_STAMP_LOG,
  type OASealRow,
  type OASealRuleRow,
  type StampBatchRow,
  type StampFailureRow,
  type StampHistoryRow,
  type StampLogRow,
} from './oa-stamp-demo'

// B3. OA 归档
export {
  DEMO_ARCHIVE_CATEGORIES,
  DEMO_ARCHIVE_LOG,
  DEMO_ARCHIVE_MATERIALS,
  type ArchiveCategoryRow,
  type ArchiveLogRow,
  type ArchiveMaterialMeta,
} from './archive-demo'

// C. 要素式转换
export {
  DEMO_CONVERT_LOG,
  DEMO_CONVERT_MAPPING,
  DEMO_CONVERT_MAPPING_DETAIL,
  DEMO_CONVERT_PREVIEW,
  DEMO_CONVERT_STATS,
  DEMO_CONVERT_TEMPLATES,
  type ConvertLogRow,
  type ConvertMappingRow,
  type ConvertPreviewField,
  type ConvertStatSummary,
  type ConvertTemplateRow,
} from './convert-demo'

// D. 一张网立案 / 法院校验
export {
  DEMO_COURT_AMOUNT_CHECK,
  DEMO_COURT_CHECK_RULES,
  DEMO_COURT_FIELD_MAPPING,
  DEMO_COURT_MATERIALS,
  DEMO_COURT_PLATFORM,
  DEMO_COURT_SUBMIT_HISTORY,
  type CourtAmountCheckRow,
  type CourtCheckRuleRow,
  type CourtFieldMappingRow,
  type CourtMaterialRow,
  type CourtSubmitHistoryRow,
} from './court-demo'

// E. 整包拆分 UI
export {
  DEMO_BUNDLE_CAPABILITIES,
  DEMO_BUNDLE_FAQ,
  DEMO_BUNDLE_RULES,
  DEMO_BUNDLE_SEGMENT_DETAIL,
  DEMO_BUNDLE_SPLIT_RECORDS,
  type BundleSegmentDetail,
  type BundleSplitRecord,
} from './bundle-demo'

// F. 起诉条件（就绪度）
export {
  DEMO_READINESS_CHECK_BASIS,
  DEMO_READINESS_FILES,
  DEMO_READINESS_HISTORY,
  DEMO_READINESS_PEERS,
  DEMO_READINESS_SLOT_META,
  type ReadinessFileRow,
  type ReadinessHistoryRow,
  type ReadinessPeerRow,
  type ReadinessSlotMeta,
} from './readiness-demo'

// G. 单案诉讼线 · 六阶段（① 收案 → ② 读懂 → ③ 缺件 → ④ 文书 → ⑤ 回扫 → ⑥ 校验）
export {
  DEMO_CONFLICT_HITS,
  DEMO_CONTRACT_GEN,
  DEMO_CONTRACT_TEMPLATES,
  DEMO_CONTRACT_TERMS,
  DEMO_FILING_CHECKS,
  DEMO_FILING_FIXES,
  DEMO_GAP_NOTICES,
  DEMO_GAP_RECEIVED,
  DEMO_GAP_TEMPLATES,
  DEMO_INTAKE_EVENTS,
  DEMO_INTAKE_SEGMENTS,
  DEMO_INTAKE_SOURCES,
  DEMO_RETURNED_DIFF,
  DEMO_RETURNED_MAILS,
  DEMO_SCAN_BATCHES,
  DEMO_SIGN_CHECKS,
  DEMO_UNDERSTAND_DOCS,
  DEMO_UNDERSTAND_FIELDS,
  DEMO_UNDERSTAND_ISSUES,
  type ConflictHitRow,
  type ContractGenRow,
  type ContractTemplateRow,
  type ContractTermRow,
  type FilingCheckRow,
  type FilingFixRow,
  type GapNoticeRow,
  type GapReceivedRow,
  type GapTemplateRow,
  type IntakeEventRow,
  type IntakeSegmentRow,
  type ReturnedDiffRow,
  type ReturnedMailRow,
  type ScanBatchRow,
  type SignCheckRow,
  type SourceFileRow,
  type UnderstandDocRow,
  type UnderstandFieldRow,
  type UnderstandIssueRow,
} from './stages-demo'

// H1. X1 · ① 收案 / ② 读懂 的下钻层（扫描件预览 / 置信度因子）
export {
  DEMO_X1_CONFIDENCE_FACTORS,
  DEMO_X1_SEGMENT_PREVIEWS,
  type X1ConfidenceFactorRow,
  type X1SegmentPreviewRow,
} from './x1-preview-demo'

// H2. X1 · 下钻层（原文对照 / 字段出处 / 追加渠道 / 转换方法）
export {
  DEMO_X1_APPEND_CHANNELS,
  DEMO_X1_CONVERT_METHODS,
  DEMO_X1_FIELD_LOCATES,
  DEMO_X1_ORIGINAL_COMPARE,
  type X1AppendChannelRow,
  type X1ConvertMethodRow,
  type X1FieldLocateRow,
  type X1OriginalCompareRow,
} from './x1-locate-demo'

// I. X2 · ③ 缺件 / ⑤ 回扫 的下钻层
export {
  DEMO_X2_ASSIGN_CANDIDATES,
  DEMO_X2_CLAIM_FILTERS,
  DEMO_X2_GAP_SCRIPTS,
  DEMO_X2_GAP_SOURCES,
  DEMO_X2_GAP_TIMELINE,
  DEMO_X2_MAIL_ATTACHMENTS,
  DEMO_X2_SCAN_INTERVALS,
  DEMO_X2_SCAN_MAILBOXES,
  type GapNoticeSourceRow,
  type GapScriptRow,
} from './x2-demo'

// J. X3 · ④ 文书 / ⑥ 校验 的下钻层
export {
  DEMO_X3_AMOUNTS,
  DEMO_X3_BROWSER_FRAMES,
  DEMO_X3_CONFLICT_REPORT,
  DEMO_X3_CONFLICT_REPORT_FILE,
  DEMO_X3_FIX_DIFF,
  DEMO_X3_NOTICE_DELIVERY,
  DEMO_X3_TEMPLATE_OPTIONS,
  DEMO_X3_TERM_DRAFTS,
  type X3AmountRow,
  type X3BrowserFrameRow,
  type X3ConflictReportRow,
  type X3FixDiffRow,
  type X3NoticeDeliveryRow,
  type X3TemplateOptionRow,
  type X3TermDraftRow,
} from './x3-demo'
