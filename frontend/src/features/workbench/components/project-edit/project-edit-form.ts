import { feeModeLabelToCode, stageLabelsToCodes, stageOptionsFor } from '../../contract-enums'
import type { ContractListItem, ContractUpdatePayload } from '../../types'

/**
 * 「项目编辑页」的表单模型与差量算法（纯函数，可单测）。
 *
 * 这一层存在的理由只有一个：写接口是 `exclude_unset` 语义——**不传=不动**，
 * 传 `null`=真的清空（而且 name/status/case_type/fee_mode/custom_terms/
 * specified_date 传 null 会 500）。所以「把整份表单原样 PUT」是错的，
 * 必须逐字段判差，只发用户真改过的那几个键。
 */

export interface ProjectEditForm {
  name: string
  caseType: string
  status: string
  /** 指定日期（YYYY-MM-DD，必有） */
  specified: string
  /** 服务期起止（'' = 空，提交 null） */
  from: string
  to: string
  isFiled: boolean
  /** 收费模式代码（FIXED / SEMI_RISK / FULL_RISK / CUSTOM） */
  feeMode: string
  /** 金额与比例都按「用户敲的字符串」保存：'' 表示未填，提交时转 null */
  fixedAmount: string
  riskRate: string
  customTerms: string
  /** 代理阶段代码数组（不是标签） */
  stages: string[]
}

/** 后端 GET 回来的是中文标签，这里翻回代码（否则原样 PUT 会被判「无效阶段」） */
export function formFromContract(c: ContractListItem): ProjectEditForm {
  return {
    name: c.name ?? '',
    caseType: c.case_type ?? 'civil',
    status: c.status ?? 'active',
    specified: c.specified_date ? String(c.specified_date).slice(0, 10) : '',
    from: c.start_date ? String(c.start_date).slice(0, 10) : '',
    to: c.end_date ? String(c.end_date).slice(0, 10) : '',
    isFiled: Boolean(c.is_filed),
    feeMode: feeModeLabelToCode(c.fee_mode),
    fixedAmount: c.fixed_amount == null ? '' : String(c.fixed_amount),
    riskRate: c.risk_rate == null ? '' : String(c.risk_rate),
    customTerms: c.custom_terms ?? '',
    stages: stageLabelsToCodes(c.representation_stages ?? []),
  }
}

const num = (s: string): number | null => {
  const t = s.trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

/** 后端把金额/比例下发成字符串（DecimalField），比较要按数值，不能按字面 */
const sameNum = (formVal: string, original: string | null | undefined): boolean => {
  const a = num(formVal)
  const b = num(original == null ? '' : String(original))
  return a === b || (a != null && b != null && Math.abs(a - b) < 1e-9)
}

/**
 * 差量：只返回用户真改过的字段。
 *
 * `confirmFinance` 单独返回，因为后端对「财务四字段」的门禁看的是**字段在不在这份
 * payload 里**（哪怕值没变也拦），前端必须先弹二次确认才能带上 `confirm_finance`。
 */
export function toUpdatePayload(
  form: ProjectEditForm,
  original: ContractListItem,
): { payload: ContractUpdatePayload; confirmFinance: boolean } {
  const payload: ContractUpdatePayload = {}

  if (form.name.trim() !== (original.name ?? '')) payload.name = form.name.trim()
  if (form.caseType !== original.case_type) payload.case_type = form.caseType
  if (form.status !== original.status) payload.status = form.status
  if (form.specified && form.specified !== String(original.specified_date ?? '').slice(0, 10)) {
    payload.specified_date = form.specified
  }
  const from = form.from || null
  const to = form.to || null
  const origFrom = original.start_date ? String(original.start_date).slice(0, 10) : null
  const origTo = original.end_date ? String(original.end_date).slice(0, 10) : null
  if (from !== origFrom) payload.start_date = from
  if (to !== origTo) payload.end_date = to
  if (form.isFiled !== Boolean(original.is_filed)) payload.is_filed = form.isFiled
  if (form.feeMode !== feeModeLabelToCode(original.fee_mode)) payload.fee_mode = form.feeMode
  if (!sameNum(form.fixedAmount, original.fixed_amount)) payload.fixed_amount = num(form.fixedAmount)
  if (!sameNum(form.riskRate, original.risk_rate)) payload.risk_rate = num(form.riskRate)
  if (form.customTerms.trim() !== (original.custom_terms ?? '').trim()) {
    payload.custom_terms = form.customTerms
  }
  const origStages = stageLabelsToCodes(original.representation_stages ?? [])
  const stagesChanged =
    form.stages.length !== origStages.length || form.stages.some((s, i) => s !== origStages[i])
  if (stagesChanged) payload.representation_stages = form.stages

  const confirmFinance = Object.keys(payload).some((k) =>
    ['fee_mode', 'fixed_amount', 'risk_rate', 'custom_terms'].includes(k),
  )
  return { payload, confirmFinance }
}

export type FormErrors = Partial<Record<keyof ProjectEditForm | 'stages' | 'fee', string>>

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/**
 * 提交前校验。
 *
 * 后端对这些**基本不拦**：日期写成 `2026/01/02` 直接 500，`risk_rate` 超 100 触发
 * DB 约束 500，案子类型/收费模式传错值反而静默落库。前端必须自己守住，
 * 不能让律师看到「系统错误,请稍后重试」。
 */
export function validateForm(form: ProjectEditForm): FormErrors {
  const e: FormErrors = {}
  const name = form.name.trim()
  if (!name) e.name = '名称不能为空'
  else if (name.length > 100) e.name = '名称最多 100 字（后端字段长度）'

  if (!form.specified) e.specified = '指定日期必填（后端该列不允许为空）'
  else if (!DATE_RE.test(form.specified)) e.specified = '日期格式应为 YYYY-MM-DD'

  for (const [key, v] of [
    ['from', form.from],
    ['to', form.to],
  ] as const) {
    if (v && !DATE_RE.test(v)) e[key] = '日期格式应为 YYYY-MM-DD'
  }
  if (form.from && form.to && !e.from && !e.to && form.from > form.to) {
    e.to = '结束日期不能早于开始日期'
  }

  const amount = num(form.fixedAmount)
  const rate = num(form.riskRate)
  if (form.fixedAmount.trim() !== '' && (amount == null || amount < 0)) e.fixedAmount = '金额应为正数'
  if (form.riskRate.trim() !== '' && (rate == null || rate <= 0 || rate > 100)) {
    e.riskRate = '风险比例应在 0–100 之间'
  }
  if (form.feeMode === 'FIXED' && !(amount != null && amount > 0)) {
    e.fee = '固定收费需填写金额'
  }
  if (form.feeMode === 'SEMI_RISK') {
    if (!(amount != null && amount > 0)) e.fee = '半风险收费需填写前期金额'
    else if (!(rate != null && rate > 0)) e.fee = '半风险收费需填写风险比例'
  }
  if (form.feeMode === 'FULL_RISK' && !(rate != null && rate > 0)) {
    e.fee = '全风险收费需填写风险比例'
  }
  if (form.feeMode === 'CUSTOM' && !form.customTerms.trim()) {
    e.fee = '自定义收费需填写条款文本'
  }

  const allowed = new Set(stageOptionsFor(form.caseType).map((s) => s.code))
  const bad = form.stages.filter((s) => !allowed.has(s))
  if (bad.length > 0) {
    e.stages = `「${bad.join('、')}」不属于当前案件类型（这类案子后端不接受这些代理阶段）`
  }
  return e
}
