/**
 * 合同枚举的**前端镜像**（代码值 ↔ 中文标签）。
 *
 * 为什么必须自己维护一份：后端 `ContractOut` 把 `fee_mode` 与
 * `representation_stages` 翻成**中文标签**下发（`contract_schemas.py` 的 resolver），
 * 而 `ContractUpdate` 收的是**代码值**。直接把 GET 的响应塞回表单再 PUT，会写进
 * 「半风险收费」「一审」这种脏值，或者被后端判「无效阶段」。
 *
 * 取值来源：`backend/apps/core/models/enums.py`（合同类型 / 阶段代码）与
 * `backend/apps/core/config/business_config.py`（每类案子可用的阶段集合）。
 * 阶段标签集合由 `contract-enums.test.ts` 与 `detail/chain-domain.ts` 的
 * STAGE_ORDER 对表锁住，漂移会红。
 */

export interface EnumOption {
  value: string
  label: string
}

/** 合同类型（后端 `CaseType`） */
export const CASE_TYPE_OPTIONS: readonly EnumOption[] = [
  { value: 'civil', label: '民商事' },
  { value: 'criminal', label: '刑事' },
  { value: 'administrative', label: '行政' },
  { value: 'labor', label: '劳动' },
  { value: 'intl', label: '涉外' },
  { value: 'special', label: '专项' },
  { value: 'advisor', label: '常法' },
]

/** 合同状态（后端 `ContractStatus`） */
export const CONTRACT_STATUS_OPTIONS: readonly EnumOption[] = [
  { value: 'unsigned', label: '未盖章' },
  { value: 'active', label: '在办' },
  { value: 'archived', label: '已归档' },
]

/** 收费模式（后端 `FeeMode`，写接口要大写代码） */
export const FEE_MODE_OPTIONS: readonly EnumOption[] = [
  { value: 'FIXED', label: '固定收费' },
  { value: 'SEMI_RISK', label: '半风险收费' },
  { value: 'FULL_RISK', label: '全风险收费' },
  { value: 'CUSTOM', label: '自定义收费' },
]

export interface StageOption {
  code: string
  label: string
  /** 该阶段对哪些 case_type 可用（后端按 case_type 校验，其余一律 400） */
  caseTypes: readonly string[]
}

/** 民商事与行政的可用阶段集合一致（后端 business_config 里就是同集） */
const CIVIL_ADMIN = ['civil', 'administrative'] as const
const CRIMINAL = ['criminal'] as const

/**
 * 18 个代理阶段。`caseTypes` 对齐后端 `business_config.CASE_STAGES` 的可用集：
 * - 涉外 / 专项 / 常法**没有**任何可用阶段（传非空数组必 400）
 * - 劳动只有劳动仲裁
 */
export const STAGE_OPTIONS: readonly StageOption[] = [
  { code: 'investigation', label: '侦查', caseTypes: CRIMINAL },
  { code: 'prosecution_review', label: '审查起诉', caseTypes: CRIMINAL },
  { code: 'labor_arbitration', label: '劳动仲裁', caseTypes: ['labor'] },
  { code: 'administrative_review', label: '行政复议', caseTypes: ['administrative'] },
  { code: 'private_prosecution', label: '自诉', caseTypes: CRIMINAL },
  { code: 'first_trial', label: '一审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'second_trial', label: '二审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'retrial_first', label: '重审一审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'retrial_second', label: '重审二审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'apply_retrial', label: '申请再审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'rehearing_first', label: '再审一审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'rehearing_second', label: '再审二审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'review', label: '提审', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'death_penalty_review', label: '死刑复核程序', caseTypes: CRIMINAL },
  { code: 'petition', label: '申诉', caseTypes: [...CIVIL_ADMIN, ...CRIMINAL] },
  { code: 'apply_protest', label: '申请抗诉', caseTypes: CRIMINAL },
  { code: 'petition_protest', label: '申诉抗诉', caseTypes: CRIMINAL },
  { code: 'enforcement', label: '执行', caseTypes: CIVIL_ADMIN },
]

/** 某类案子可选的阶段（空数组 = 这类案子不该出现阶段选择器） */
export function stageOptionsFor(caseType: string | null | undefined): StageOption[] {
  if (!caseType) return []
  return STAGE_OPTIONS.filter((s) => s.caseTypes.includes(caseType))
}

export function feeModeCodeToLabel(code: string | null | undefined): string {
  return FEE_MODE_OPTIONS.find((o) => o.value === code)?.label ?? code ?? ''
}

/** 后端 GET 回的是标签；认不出（历史脏值）时原样返回，由校验拦住 */
export function feeModeLabelToCode(label: string | null | undefined): string {
  if (!label) return 'FIXED'
  return FEE_MODE_OPTIONS.find((o) => o.label === label)?.value ?? label
}

export function stageCodesToLabels(codes: readonly string[]): string[] {
  return codes.map((c) => STAGE_OPTIONS.find((s) => s.code === c)?.label ?? c)
}

/** 标签 → 代码；认不出的标签原样返回（脏数据不该被静默吞掉） */
export function stageLabelsToCodes(labels: readonly string[]): string[] {
  return labels.map((l) => STAGE_OPTIONS.find((s) => s.label === l)?.code ?? l)
}

export function optionLabel(options: readonly EnumOption[], value: string | null | undefined): string {
  return options.find((o) => o.value === value)?.label ?? value ?? ''
}
