/**
 * 演示数据 · G2. ② 读懂
 *
 * 机器读出来的东西：文档清单（含摘录）、关键字段、读不懂的问题。
 */

// ───────────────────────── ② 读懂 · 文档清单 ─────────────────────────

export interface UnderstandDocRow {
  fileName: string
  type: string
  chars: number
  pages: number
  method: '原生PDF' | 'OCR' | '表格还原'
  quality: 'high' | 'medium'
  /** markdown 首段摘录 */
  excerpt: string
}

export const DEMO_UNDERSTAND_DOCS: UnderstandDocRow[] = [
  {
    fileName: '个人购房借款担保合同',
    type: '借款合同',
    chars: 12480,
    pages: 14,
    method: '原生PDF',
    quality: 'high',
    excerpt: '## 个人购房借款/担保合同\n\n**合同编号**：DEMO202100000001\n**借款人**：谭某某\n**贷款人**：某某银行某某支行\n\n### 第一条 贷款金额\n贷款金额为人民币 **820,000.00 元**（大写：捌拾贰万元整）。',
  },
  {
    fileName: '借款借据及放款凭证',
    type: '放款凭证',
    chars: 860,
    pages: 2,
    method: '原生PDF',
    quality: 'high',
    excerpt: '## 借款借据\n\n兹借到人民币 820,000.00 元，期限自 2019-03-18 至 2039-03-18。\n\n放款日期：2019-03-18　放款账号：6210 **** **** 3321',
  },
  {
    fileName: '还款明细表（2019-2026）',
    type: '还款明细',
    chars: 6420,
    pages: 8,
    method: '表格还原',
    quality: 'high',
    excerpt: '## 还款明细\n\n| 期次 | 应还日期 | 应还本息 | 实还 | 逾期天数 |\n|---|---|---|---|---|\n| 1 | 2019-04-18 | 5,432.11 | 5,432.11 | 0 |\n| … | | | | |\n| 85 | 2026-04-18 | 5,432.11 | 0.00 | 198 |',
  },
  {
    fileName: '还款账户流水',
    type: '银行流水',
    chars: 9180,
    pages: 6,
    method: '表格还原',
    quality: 'medium',
    excerpt: '## 账户交易明细\n\n| 日期 | 摘要 | 金额 | 余额 |\n|---|---|---|---|\n| 2026-01-18 | 代扣 | 5,432.11 | 1,204.88 |\n| 2026-02-18 | 代扣失败 | 0.00 | 1,204.88 |',
  },
]

// ───────────────────────── ② 读懂 · 关键字段 ─────────────────────────

export interface UnderstandFieldRow {
  doc: string
  field: string
  value: string
  confidence: number
  source: string
}

export const DEMO_UNDERSTAND_FIELDS: UnderstandFieldRow[] = [
  { doc: '借款合同', field: '合同编号', value: 'DEMO202100000001', confidence: 0.99, source: '第 1 页首行' },
  { doc: '借款合同', field: '借款人', value: '谭某某', confidence: 0.98, source: '第 1 页当事人栏' },
  { doc: '借款合同', field: '贷款金额', value: '¥820,000.00', confidence: 0.99, source: '第一条 贷款金额' },
  { doc: '借款合同', field: '借款期限', value: '2019-03-18 至 2039-03-18', confidence: 0.97, source: '第二条 借款期限' },
  { doc: '借款合同', field: '年利率', value: '4.90%', confidence: 0.96, source: '第四条 利率' },
  { doc: '借款合同', field: '逾期罚息', value: '约定利率上浮 50%', confidence: 0.95, source: '第九条 违约责任' },
  { doc: '借款合同', field: '管辖法院', value: '合同签订地人民法院', confidence: 0.88, source: '第十七条 争议解决' },
  { doc: '还款明细', field: '已还期数', value: '84 期', confidence: 0.99, source: '表格行数统计' },
  { doc: '还款明细', field: '逾期期数', value: '12 期', confidence: 0.98, source: '逾期天数列' },
  { doc: '还款明细', field: '最后还款日', value: '2026-04-18', confidence: 0.97, source: '表格末行' },
  { doc: '催收记录', field: '催收次数', value: '电话 11 次 / 上门 3 次', confidence: 0.94, source: '记录汇总页' },
  { doc: '催收记录', field: '最后催收日', value: '2025-06-12', confidence: 0.93, source: '记录末条' },
]

// ───────────────────────── ② 读懂 · 问题清单 ─────────────────────────

export interface UnderstandIssueRow {
  doc: string
  issue: string
  impact: string
  action: string
}

export const DEMO_UNDERSTAND_ISSUES: UnderstandIssueRow[] = [
  { doc: '差额补足承诺函', issue: '落款日期被红色印章覆盖', impact: '抽不到签署日期，影响生效时间判断', action: '已标记待人工核对' },
  { doc: '催收记录', issue: '手写批注部分 OCR 置信度 0.58', impact: '催收次数可能少算', action: '已保留原图，律师可对照' },
  { doc: '还款账户流水', issue: '表格跨页断行，第 4-5 页表头重复', impact: '需按表头重新拼表', action: '已自动拼表，标记需复核' },
]
