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

/**
 * 预选收款的确定性。
 *
 * 红票两档单列（后端 `PaymentPickConfidence` 同名常量）：红票的收款永远选不出来
 * （冲销不是收款），给它一个「金额对上了」的档位等于谎报确定性。
 */
export type PaymentPickConfidence =
  | 'exact'
  | 'amount_mismatch'
  | 'ambiguous'
  | 'no_payment'
  | 'red_offset'
  | 'red_unmatched'

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

/**
 * 红票冲销的原票（契约 `OffsetInvoiceOut`）。
 *
 * 与下面的 {@link GroupItem} 不同：这一个是**库里的合同发票**（`contracts.Invoice`），
 * 不是待认领记录——所以只有 `invoice_id` 形态的字段，没有 intake 侧 id。
 */
export interface OffsetInvoice {
  id: number
  invoice_number: string
  total_amount: string | null
  contract_id: number
  contract_name: string
  folder_subpath: string
}

/** 红票组里的一个成员（契约 `GroupItemOut`）：可能还没落成发票，故两个 id 都可空 */
export interface GroupItem {
  intake_id: number | null
  invoice_id: number | null
  invoice_number: string
  total_amount: string | null
}

/**
 * 冲红重开的三张票（契约 `RedGroupOut`）：原票 → 红票 → 重开的新蓝票。
 *
 * 后端按「同号原票 + 冲销关系」聚组下发；`original` 为 null 表示被冲销的原票
 * 不在系统里（历史票 / 别家开的票），此时只能人工处理，不能一键冲红重开。
 */
export interface RedGroup {
  group_key: string
  original: GroupItem | null
  red: GroupItem
  reissue: GroupItem | null
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

  // ── 红字发票（红冲）相关：全部由后端按契约下发 ─────────────

  /** 是否红字发票。后端按票面事实判：有被冲票号 **或** 金额为负 */
  is_red: boolean
  /** 被红冲的原蓝票号（空串 = 未识别到，不是「没有」） */
  red_against_number: string
  /** 红字发票信息确认单编号 */
  red_confirmation_no: string
  /** 被冲销的原票（查到了才有；不在系统里为 null） */
  offset_invoice: OffsetInvoice | null
  /** 本票冲掉的那条待认领记录 */
  supersedes_intake_id: number | null
  /** 冲掉本票的那条待认领记录 */
  superseded_by_intake_id: number | null
  /** 冲红重开整组的展开（不在任何组里为 null） */
  reatch_group: RedGroup | null
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
