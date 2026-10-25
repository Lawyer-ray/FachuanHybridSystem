/**
 * 合同/案件类型代码 → 诉讼 / 非诉 判定。
 *
 * 代码值与后端 `core.models.enums.CaseType` 对齐：诉讼类
 * civil / criminal / administrative / labor / intl，其余（special / advisor）为非诉。
 * workbench（项目列表分组）与 search（全局检索路由分流）两域共用，
 * 单一来源防止两处集合漂移。
 */

/** 诉讼类 case_type 代码集合（其余视为非诉） */
export const LITIGATION_CASE_TYPES: ReadonlySet<string> = new Set([
  'civil',
  'criminal',
  'administrative',
  'labor',
  'intl',
])

/** 合同的 case_type 是否诉讼类（决定详情路由 /projects/:id 还是 /projects/:id/nonlit） */
export const isLitigationType = (caseType: string | null | undefined): boolean =>
  caseType != null && LITIGATION_CASE_TYPES.has(caseType)
