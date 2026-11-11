/**
 * 演示数据 · D. 一张网立案 / 法院校验
 *
 * 前缀 DEMO_COURT_*。
 * 真实功能上线时整个文件删除即可。
 */

export interface CourtFieldMappingRow {
  /** 法穿侧字段名 */
  from: string
  /** 一张网表单字段名 */
  to: string
  /** 本次要填进去的值（已按法院口径格式化） */
  value: string
  /** mapped=自动填好；confirm=机器拿不准，要律师看一眼 */
  status: 'mapped' | 'confirm'
  /** confirm 状态下说明为什么要人看 */
  note?: string
}

export const DEMO_COURT_FIELD_MAPPING: CourtFieldMappingRow[] = [
  { from: '案件名称', to: '案件名称', value: '某某银行广州分行诉谭某某金融借款合同纠纷', status: 'mapped' },
  { from: '案由', to: '案由（三级）', value: '金融借款合同纠纷', status: 'mapped' },
  { from: '原告名称', to: '原告（全称）', value: '某某银行广州分行', status: 'mapped' },
  { from: '原告类型', to: '原告主体类型', value: '法人 / 其他组织', status: 'mapped' },
  { from: '统一社会信用代码', to: '原告证件号码', value: '9144XX XXXX XXXX XXXX', status: 'confirm', note: '营业执照扫描件与案件登记值末两位不一致，建议核对原件' },
  { from: '被告名称', to: '被告（姓名）', value: '谭某某', status: 'mapped' },
  { from: '被告身份证号', to: '被告证件号码', value: '4401XX XXXX XXXX XXXX', status: 'mapped' },
  { from: '被告送达地址', to: '被告送达地址', value: '广州市天河区某某街道某某路 X 号', status: 'confirm', note: '合同约定地址与户籍地址不同，需确认以哪一个送达' },
  { from: '标的额', to: '诉讼标的额（元）', value: '998,670.21', status: 'confirm', note: '与起诉状标的额差 31.85 元，见下方三处金额校验' },
  { from: '诉讼请求（本金）', to: '请求事项·本金', value: '820,000.00', status: 'mapped' },
  { from: '诉讼请求（利息）', to: '请求事项·利息', value: '178,670.21', status: 'mapped' },
  { from: '管辖法院', to: '受诉法院', value: '广州市天河区人民法院', status: 'mapped' },
  { from: '立案类型', to: '案件类别', value: '民事一审', status: 'mapped' },
  { from: '承办律师', to: '代理人姓名', value: '黄某某', status: 'mapped' },
]

export interface CourtAmountCheckRow {
  item: string
  /** 起诉状（要素式文书）上的数 */
  fromPleading: string
  /** 一张网立案表单里填的数 */
  fromCourtForm: string
  /** 要素式结构化字段里的数 */
  fromElement: string
  /** 三处是否一致 */
  ok: boolean
  /** 差异说明（ok=false 时必填） */
  diff?: string
}

export const DEMO_COURT_AMOUNT_CHECK: CourtAmountCheckRow[] = [
  { item: '本金', fromPleading: '820,000.00', fromCourtForm: '820,000.00', fromElement: '820,000.00', ok: true },
  { item: '利息', fromPleading: '178,638.36', fromCourtForm: '178,670.21', fromElement: '178,638.36', ok: false, diff: '立案表单标的额被人工改动，差 31.85 元' },
  { item: '罚息', fromPleading: '0.00', fromCourtForm: '0.00', fromElement: '0.00', ok: true },
  { item: '复利', fromPleading: '0.00', fromCourtForm: '0.00', fromElement: '0.00', ok: true },
  { item: '诉讼费（预交）', fromPleading: '13,786.00', fromCourtForm: '13,786.00', fromElement: '13,786.00', ok: true },
  { item: '合计', fromPleading: '998,638.36', fromCourtForm: '998,670.21', fromElement: '998,638.36', ok: false, diff: '合计随利息一并偏差 31.85 元，递交前须回到起诉状口径' },
]

export interface CourtSubmitHistoryRow {
  id: string
  at: string
  /** 批次号：一次递交一个批次，重试会新开批次 */
  batch: string
  filingNumber: string
  result: 'accepted' | 'returned' | 'failed' | 'pending'
  /** 法院受理号 / 退回单号 */
  receipt: string
}

export const DEMO_COURT_SUBMIT_HISTORY: CourtSubmitHistoryRow[] = [
  { id: 'cs_1', at: '2026-11-03 10:03', batch: 'B-20261103-0031', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261103008812' },
  { id: 'cs_2', at: '2026-11-02 17:26', batch: 'B-20261102-0047', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261102001465' },
  { id: 'cs_3', at: '2026-11-02 15:08', batch: 'B-20261102-0042', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_4', at: '2026-11-01 16:41', batch: 'B-20261101-0038', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261101000932' },
  { id: 'cs_5', at: '2026-10-30 11:19', batch: 'B-20261030-0026', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261030005117' },
  { id: 'cs_6', at: '2026-10-29 15:54', batch: 'B-20261029-0022', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_7', at: '2026-10-29 09:33', batch: 'B-20261029-0019', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261029000671' },
  { id: 'cs_8', at: '2026-10-28 14:07', batch: 'B-20261028-0015', filingNumber: '（20XX）粤0106民初XXXX号', result: 'pending', receipt: '待法院处理' },
  { id: 'cs_9', at: '2026-10-27 10:22', batch: 'B-20261027-0011', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_10', at: '2026-10-26 16:48', batch: 'B-20261026-0008', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261026000418' },
  { id: 'cs_11', at: '2026-10-26 09:15', batch: 'B-20261026-0004', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_12', at: '2026-10-24 11:02', batch: 'B-20261024-0003', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261024002233' },
]

export interface CourtMaterialRow {
  id: string
  name: string
  /** 页数 */
  pages: number
  /** 盖章状态 */
  stamp: 'stamped' | 'partial' | 'none'
  /** 上传时间（未上传为空） */
  uploadedAt: string | null
}

export const DEMO_COURT_MATERIALS: CourtMaterialRow[] = [
  { id: 'cm_1', name: '民事起诉状（要素式）.pdf', pages: 4, stamp: 'stamped', uploadedAt: '11-03 09:40' },
  { id: 'cm_2', name: '证据目录及证据材料.pdf', pages: 46, stamp: 'stamped', uploadedAt: '11-03 09:42' },
  { id: 'cm_3', name: '当事人身份证明材料.pdf', pages: 6, stamp: 'stamped', uploadedAt: '11-03 09:43' },
  { id: 'cm_4', name: '授权委托书（含代理人证）.pdf', pages: 3, stamp: 'stamped', uploadedAt: '11-03 09:44' },
  { id: 'cm_5', name: '律师事务所函.pdf', pages: 1, stamp: 'stamped', uploadedAt: '11-03 09:44' },
  { id: 'cm_6', name: '送达地址确认书.pdf', pages: 1, stamp: 'partial', uploadedAt: '11-03 09:45' },
  { id: 'cm_7', name: '借款合同及借据.pdf', pages: 12, stamp: 'stamped', uploadedAt: '11-03 09:46' },
  { id: 'cm_8', name: '放款凭证与还款明细.pdf', pages: 18, stamp: 'none', uploadedAt: '11-03 09:47' },
  { id: 'cm_9', name: '催收记录（含公告）.pdf', pages: 9, stamp: 'none', uploadedAt: null },
  { id: 'cm_10', name: '诉讼费预交凭证.pdf', pages: 1, stamp: 'none', uploadedAt: null },
]

export const DEMO_COURT_PLATFORM = {
  courtName: '广州市天河区人民法院',
  courtCode: '440106',
  filingChamber: '立案庭（民商事立案窗口）',
  phone: '020-XXXX XXXX',
  workTime: '工作日 08:30–12:00 / 14:00–17:30',
  onlineChannel: '广东法院诉讼服务网 · 网上立案',
  address: '广州市天河区某某街道某某大道 X 号',
  notices: [
    '网上立案后 3 个工作日内答复，退回补正的需在 7 日内重新递交，逾期视为撤回。',
    '起诉状须使用要素式文本并加盖公章，落款日期与递交日期一致。',
    '证据材料按 PDF 上传，单份不超过 50 MB，扫描分辨率不低于 200 dpi。',
    '送达地址确认书须由当事人本人或法定代表人签章，代理人代签需另附授权。',
    '同一原告同批次案件的诉讼费可合并预交，但每案须单独附缴费凭证。',
  ],
} as const

export interface CourtCheckRuleRow {
  id: 'amount' | 'party' | 'jurisdiction'
  title: string
  /** 比对的字段 */
  fields: string
  /** 判定口径 */
  rule: string
  /** 不一致时的处理 */
  onFail: 'block' | 'warn'
}

export const DEMO_COURT_CHECK_RULES: CourtCheckRuleRow[] = [
  {
    id: 'amount',
    title: '金额校验',
    fields: '起诉状标的额 ↔ 一张网表单标的额 ↔ 要素式字段',
    rule: '三处逐项比对（本金 / 利息 / 罚息 / 复利 / 合计），允许误差 0.00 元；任一项不一致即阻断递交。',
    onFail: 'block',
  },
  {
    id: 'party',
    title: '当事人校验',
    fields: '原告 / 被告名称与证件号 ↔ 身份证明材料',
    rule: '名称须与营业执照/身份证 OCR 结果完全一致；法人须校验统一社会信用代码，自然人须校验身份证号。',
    onFail: 'warn',
  },
  {
    id: 'jurisdiction',
    title: '管辖校验',
    fields: '被告住所地 / 合同履行地 ↔ 受诉法院',
    rule: '按合同约定管辖优先；无约定时取被告住所地或合同履行地基层法院。级别管辖按标的额定位。',
    onFail: 'warn',
  },
]
