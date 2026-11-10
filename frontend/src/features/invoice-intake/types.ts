/**
 * 发票待认领（Invoice Intake）数据模型。
 *
 * 业务：律师给客户开票后由律所财务通过邮件发来发票 PDF，系统解析出
 * 「律所项目号 / 购买方 / 金额」并匹配到项目，**提醒律师确认绑定**。
 *
 * 与 `features/payment-intake` 的 `Intake` 同构（同一套「系统建议 → 人工裁定」模型），
 * 但字段完全独立：feature 之间禁止互相 import，形状相似不等于可以共用类型。
 */

/** 待认领状态（与后端 `InvoiceIntakeStatus` 一一对应） */
export type InvoiceIntakeStatus = 'pending' | 'confirmed' | 'rejected'

/** 匹配信号等级：S1 项目号确定性 > S2 案由文字 > S3 购买方名 */
export type InvoiceMatchKind = 'project_code' | 'case_text' | 'party_name'

/** 预选收款的确定性 */
export type PaymentPickConfidence = 'exact' | 'amount_mismatch' | 'ambiguous' | 'no_payment'

/** 系统给出的候选项目 */
export interface InvoiceCandidate {
  contract_id: number
  contract_name: string
  kind: InvoiceMatchKind
  score: number
  reasons: string[]
  caveat: string
}

/** 预选收款下拉项 */
export interface InvoicePaymentOption {
  id: number
  amount: string
  received_at: string
  note: string
}

/** 一条待认领发票 */
export interface InvoiceIntake {
  id: number
  invoice_number: string
  invoice_date: string | null
  total_amount: string | null
  /** 已脱敏（后端已去掉「（个人）」后缀） */
  buyer_name: string
  project_code: string
  remark: string
  status: InvoiceIntakeStatus
  status_label: string
  suggested_contract_id: number | null
  suggested_contract_name: string | null
  suggested_payment_id: number | null
  payment_pick_confidence: PaymentPickConfidence | null
  payment_pick_note: string
  payment_options: InvoicePaymentOption[]
  confirmed_contract_id: number | null
  confirmed_contract_name: string | null
  confirmed_payment_id: number | null
  invoice_id: number | null
  /** 确认后生成的重命名文件名（`发票（合同名）_YYYYMMDD开具.pdf`）；未确认为空串。
   *  行内直接展示并可复制，不靠前端自己拼——命名规则只有后端一份。 */
  invoice_display_filename: string
  /** 确认后镜像到合同文件夹的相对落点（未镜像为空串），详情里告诉律师「文件落在哪」 */
  invoice_folder_subpath: string
  candidates: InvoiceCandidate[]
  excluded_hints: { contract_id: number; contract_name: string; excluded_by: string; note: string }[]
  inbox_message_id: number
  subject: string
  sender: string
  /** 附件相对 MEDIA_ROOT 的路径（详情里展示原始文件名与去邮件的入口） */
  original_filename?: string
}

/** 操作（确认/驳回/撤销）的返回 */
export interface InvoiceActionResult {
  success: boolean
  message: string
  intake_id: number
  status: InvoiceIntakeStatus
  invoice_id: number | null
  /** 确认后生成的重命名文件名（未确认时为空串） */
  invoice_display_filename?: string
}

/** 复制发票文件到系统剪贴板的结果（与项目详情页 copy-to-clipboard 同口径） */
export interface InvoiceCopyResult {
  success: boolean
  copied: number
  reason: string
}

/** 「换个项目」下拉项：复用与款项同名结构 */
export interface SelectableContract {
  id: number
  name: string
  fee_mode: string
  fixed_amount: string | null
  paid_total: string | null
  outstanding_amount: string | null
  expires_note: string
}
