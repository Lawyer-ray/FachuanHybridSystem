/**
 * 演示数据 · J. X3 · ④ 文书 / ⑥ 校验 的细化交互数据
 *
 * 前缀 DEMO_X3_*：合同条款草稿 / 模板下拉 / 利冲报告与录屏帧 /
 * 三处金额对比 / 一键修正 diff / 通知送达 / 利冲报告导出文件名。
 * `DEMO_X3_TERM_DRAFTS` 以 stages-demo.ts 的 DEMO_CONTRACT_TERMS 为初值。
 * 真实功能上线时整个文件删除即可。
 */

import { DEMO_CONTRACT_TERMS } from './stages-demo'

export interface X3TermDraftRow {
  clause: string
  value: string
  /** 律师改过就记一句改了什么，回显「已修改」用 */
  editedTo?: string
}

export const DEMO_X3_TERM_DRAFTS: X3TermDraftRow[] = DEMO_CONTRACT_TERMS.map((t) => ({
  clause: t.clause,
  value: t.value,
}))

export interface X3TemplateOptionRow {
  id: string
  name: string
  /** 自定义模板要带一句说明，免得律师以为系统内置 */
  note: string
}

export const DEMO_X3_TEMPLATE_OPTIONS: X3TemplateOptionRow[] = [
  { id: 'v3.2', name: 'v3.2（应收案件用 · 2026-09 修订）', note: '现行版本' },
  { id: 'v2.8', name: 'v2.8（风险代理 · 2026-08 归档）', note: '旧版，仅风险代理选它' },
  { id: 'custom', name: '自定义模板…', note: '上传 .docx 后由管理员审核' },
]

export interface X3ConflictReportRow {
  title: string
  value: string
}

export const DEMO_X3_CONFLICT_REPORT: X3ConflictReportRow[] = [
  { title: '报告编号', value: 'LCA-20261101-0007' },
  { title: '检索时间', value: '11-01 10:22 — 10:24' },
  { title: '检索库', value: '律所 OA 当事人库（在办 + 历史）' },
  { title: '检索主体', value: '6 方（原告 1 · 被告 2 · 共同借款人 1 · 抵押人 2）' },
  { title: '红色冲突', value: '1 处 — 李某某（与本所在办「李某某离婚案」同证件号）' },
  { title: '黄色提示', value: '1 处 — 某某置业公司（历史委托已结案 3 年）' },
  { title: '结论', value: '存在禁止性冲突，建议终止本次委托或取得双方书面同意' },
]

export interface X3BrowserFrameRow {
  /** 地址栏里的 URL */
  url: string
  /** 这一帧正在做什么 */
  action: string
  /** 画面里被点亮的字段 */
  fields: string[]
  /** 高亮方式：命中用红，普通推进用蓝 */
  tone: 'normal' | 'hit'
}

export const DEMO_X3_BROWSER_FRAMES: X3BrowserFrameRow[] = [
  {
    url: 'https://oa.某某律所.com/login',
    action: '打开律所 OA 登录页',
    fields: ['账号', '密码'],
    tone: 'normal',
  },
  {
    url: 'https://oa.某某律所.com/party/search',
    action: '进入当事人库检索，输入「李某某」',
    fields: ['检索对象 · 李某某', '证件号 · 44XXXXXXXXXXXX01'],
    tone: 'normal',
  },
  {
    url: 'https://oa.某某律所.com/party/search?q=李某某',
    action: '返回 3 条命中，逐条比对证件号',
    fields: ['命中 1 · 李某某（离婚案 · 在办）', '命中 2 · 李某某（已结案）', '命中 3 · 李某某（同名不同人）'],
    tone: 'normal',
  },
  {
    url: 'https://oa.某某律所.com/party/search?q=李某某',
    action: '证件号 44XXXXXXXXXXXX01 完全一致 —— 红色冲突',
    fields: ['命中 1 · 李某某（离婚案 · 在办）'],
    tone: 'hit',
  },
  {
    url: 'https://oa.某某律所.com/case/create/blocked',
    action: '停止建卷，保留利冲结果页快照',
    fields: ['建卷按钮 · 已置灰', '快照 · conflict-20261101-1024.png'],
    tone: 'hit',
  },
]

export interface X3AmountRow {
  item: string
  /** 起诉状定稿的金额 */
  complaint: string
  /** 一张网立案表单回读的金额 */
  filingForm: string
  /** 要素式起诉状里的金额 */
  elements: string
  /** 差额定下的口径：不一样才算差异行 */
  consistent: boolean
  /** 差异金额 */
  delta: string
  /** 点开看到的计算口径 */
  basis: string
}

export const DEMO_X3_AMOUNTS: X3AmountRow[] = [
  {
    item: '本金',
    complaint: '¥820,000.00',
    filingForm: '¥820,000.00',
    elements: '¥820,000.00',
    consistent: true,
    delta: '0.00',
    basis: '借款合同第一条贷款金额，扣减已还本金后余额',
  },
  {
    item: '利息（截至 2026-10-31）',
    complaint: '¥96,412.35',
    filingForm: '¥96,412.35',
    elements: '¥96,412.35',
    consistent: true,
    delta: '0.00',
    basis: '年利率 4.90%，按合同约定计息方式逐期累加',
  },
  {
    item: '罚息',
    complaint: '¥71,258.86',
    filingForm: '¥71,290.71',
    elements: '¥71,258.86',
    consistent: false,
    delta: '31.85',
    basis: '立案表单重算时用了 365 天口径，起诉状按 360 天口径；差 31.85 元',
  },
  {
    item: '复利',
    complaint: '¥6,999.00',
    filingForm: '¥6,999.00',
    elements: '¥6,999.00',
    consistent: true,
    delta: '0.00',
    basis: '对未付利息按罚息利率计收复利，逐月结算',
  },
  {
    item: '诉讼费（预估）',
    complaint: '¥4,000.00',
    filingForm: '¥4,000.00',
    elements: '¥4,000.00',
    consistent: true,
    delta: '0.00',
    basis: '按争议标的额套《诉讼费用交纳办法》分段累计',
  },
  {
    item: '合计',
    complaint: '¥998,670.21',
    filingForm: '¥998,702.06',
    elements: '¥998,670.21',
    consistent: false,
    delta: '31.85',
    basis: '三处取起诉状定稿为基准；立案表单差 31.85 元来自罚息口径',
  },
]

export interface X3FixDiffRow {
  item: string
  field: string
  before: string
  after: string
}

export const DEMO_X3_FIX_DIFF: X3FixDiffRow[] = [
  { item: '金额三处不一致', field: '立案表单 · 罚息金额', before: '¥71,290.71', after: '¥71,258.86' },
  { item: '金额三处不一致', field: '立案表单 · 争议标的总额', before: '¥998,702.06', after: '¥998,670.21' },
  { item: '金额三处不一致', field: '立案表单 · 诉讼费预交金额', before: '¥4,000.31', after: '¥4,000.00' },
  { item: '要素式起诉状待转换', field: '起诉状格式', before: '传统格式（4 页）', after: '要素式（3 页 · 法院模板 2026 版）' },
  { item: '要素式起诉状待转换', field: '要素表字段', before: '未生成', after: '已生成 18 项要素（含借款合意、给付方式）' },
]

export interface X3NoticeDeliveryRow {
  channel: string
  target: string
  at: string
  state: 'sent' | 'read' | 'failed'
}

export const DEMO_X3_NOTICE_DELIVERY: X3NoticeDeliveryRow[] = [
  { channel: '站内待办', target: '主办律师 黄某某', at: '11-01 15:20', state: 'read' },
  { channel: '短信', target: '138****XXXX', at: '11-01 15:20', state: 'sent' },
  { channel: 'AI 助手卡片', target: '工作台 · 待办区', at: '11-01 15:20', state: 'read' },
]

export const DEMO_X3_CONFLICT_REPORT_FILE = 'LCA-20261101-0007 利冲审查报告.pdf'
