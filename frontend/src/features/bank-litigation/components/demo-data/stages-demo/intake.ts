/**
 * 演示数据 · G1. ① 收案
 *
 * 一叠扫描件进门：分段结果、处理事件流、源文件清单。
 */

// ───────────────────────── ① 收案 · 材料分段 ─────────────────────────

export interface IntakeSegmentRow {
  seq: number
  fileName: string
  type: string
  pages: string
  confidence: number
  status: 'ok' | 'review' | 'unrecognized'
  note: string
}

export const DEMO_INTAKE_SEGMENTS: IntakeSegmentRow[] = [
  { seq: 1, fileName: '个人购房借款担保合同', type: '借款合同', pages: 'P1–14', confidence: 0.98, status: 'ok', note: '建行标准版，骑缝完整' },
  { seq: 2, fileName: '借款借据及放款凭证', type: '放款凭证', pages: 'P15–16', confidence: 0.97, status: 'ok', note: '金额 820,000.00 元' },
  { seq: 3, fileName: '还款明细表（2019-2026）', type: '还款明细', pages: 'P17–24', confidence: 0.95, status: 'ok', note: '共 84 期，逾期 12 期' },
  { seq: 4, fileName: '催收记录汇总', type: '催收记录', pages: 'P25–28', confidence: 0.93, status: 'ok', note: '电话 11 次 / 上门 3 次' },
  { seq: 5, fileName: '借款人身份证复印', type: '身份证明', pages: 'P29', confidence: 0.99, status: 'ok', note: '正反面同页' },
  { seq: 6, fileName: '差额补足承诺函', type: '担保文件', pages: 'P30–31', confidence: 0.61, status: 'review', note: '落款日期被印章遮盖，需人工核' },
  { seq: 7, fileName: '（未识别）手写便签', type: '未识别', pages: 'P32', confidence: 0.24, status: 'unrecognized', note: '疑似银行内部批注，非案件材料' },
  { seq: 8, fileName: '还款账户流水', type: '银行流水', pages: 'P33–38', confidence: 0.96, status: 'ok', note: '与明细表勾稽一致' },
]

// ───────────────────────── ① 收案 · 处理事件 ─────────────────────────

export interface IntakeEventRow {
  at: string
  event: string
  detail: string
  ms: number
}

export const DEMO_INTAKE_EVENTS: IntakeEventRow[] = [
  { at: '10-28 09:41', event: '客户上传', detail: '王某某 通过客户链接上传 银行个贷不良_首批材料.zip', ms: 0 },
  { at: '10-28 09:41', event: '自动下载', detail: '12.4 MB · 6 个源文件', ms: 1240 },
  { at: '10-28 09:42', event: '合并整包', detail: '6 个源文件 → 38 页单一 PDF', ms: 860 },
  { at: '10-28 09:42', event: '页面识别', detail: '逐页文本提取 + 版式判断', ms: 4200 },
  { at: '10-28 09:43', event: '分段完成', detail: '识别出 8 份材料，其中 2 份需人工确认', ms: 2100 },
  { at: '10-28 09:43', event: '自动归案', detail: '6 份高置信度材料已挂到本案', ms: 680 },
  { at: '10-28 09:44', event: '通知律师', detail: '待核对 2 份，已在待办里提醒', ms: 120 },
]

// ───────────────────────── ① 收案 · 源文件 ─────────────────────────

export interface SourceFileRow {
  name: string
  size: string
  pages: number
  kind: string
}

export const DEMO_INTAKE_SOURCES: SourceFileRow[] = [
  { name: '借款合同.pdf', size: '3.2 MB', pages: 14, kind: 'PDF 原生' },
  { name: '借据.pdf', size: '0.4 MB', pages: 2, kind: 'PDF 扫描' },
  { name: '还款明细.xlsx', size: '0.2 MB', pages: 8, kind: '表格' },
  { name: '催收记录.pdf', size: '1.8 MB', pages: 4, kind: 'PDF 扫描' },
  { name: '身份证.jpg', size: '1.1 MB', pages: 1, kind: '图片' },
  { name: '流水.pdf', size: '5.7 MB', pages: 9, kind: 'PDF 扫描' },
]
