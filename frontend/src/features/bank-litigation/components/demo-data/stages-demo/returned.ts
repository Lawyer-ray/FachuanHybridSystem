/**
 * 演示数据 · G5. ⑤ 回扫
 *
 * 回扫进来的邮件与扫描件，以及补齐前后的对比。
 */

// ───────────────────────── ⑤ 回扫 · 归案邮件 ─────────────────────────

export interface ReturnedMailRow {
  subject: string
  from: string
  attachments: number
  matchedCase: string
  matchedBy: string
  action: string
  at: string
}

export const DEMO_RETURNED_MAILS: ReturnedMailRow[] = [
  { subject: 'Re: 谭某某案 补充材料', from: '客户经理 王某某', attachments: 2, matchedCase: '谭某某金融借款', matchedBy: '案号 + 当事人名', action: '已自动下载并归案', at: '11-01 09:12' },
  { subject: '扫描件-不动产权证', from: '行政 陈某某', attachments: 1, matchedCase: '谭某某金融借款', matchedBy: '文件名关键词', action: '已自动归案', at: '11-01 10:05' },
  { subject: '（20XX）粤0106民初XXXX号 受理通知书', from: '法院短信转发', attachments: 1, matchedCase: '谭某某金融借款', matchedBy: '案号精确匹配', action: '已归案并回填案号', at: '11-01 11:30' },
  { subject: 'FW: 律师函签收回执', from: '客户 李某某', attachments: 1, matchedCase: '待人工确认', matchedBy: '匹配度 62%，低于阈值', action: '已放入待处理', at: '11-01 13:48' },
]

// ───────────────────────── ⑤ 回扫 · 扫描批次 ─────────────────────────

export interface ScanBatchRow {
  batch: string
  scannedAt: string
  pages: number
  matched: string
  confidence: number
  status: 'auto' | 'manual'
}

export const DEMO_SCAN_BATCHES: ScanBatchRow[] = [
  { batch: '行政扫描_11-01_0920', scannedAt: '11-01 09:20', pages: 12, matched: '谭某某金融借款', confidence: 0.96, status: 'auto' },
  { batch: '行政扫描_11-01_1005', scannedAt: '11-01 10:05', pages: 4, matched: '谭某某金融借款', confidence: 0.94, status: 'auto' },
  { batch: '行政扫描_11-01_1430', scannedAt: '11-01 14:30', pages: 8, matched: '其他案件（2 件候选）', confidence: 0.71, status: 'manual' },
]

// ───────────────────────── ⑤ 回扫 · 补齐前后对比 ─────────────────────────

export interface ReturnedDiffRow {
  stage: string
  before: string
  after: string
  delta: string
}

export const DEMO_RETURNED_DIFF: ReturnedDiffRow[] = [
  { stage: '材料份数', before: '8 份', after: '12 份', delta: '+4' },
  { stage: '总页数', before: '38 页', after: '62 页', delta: '+24' },
  { stage: '缺件项', before: '5 项', after: '3 项', delta: '-2' },
  { stage: '硬阻塞', before: '3 项', after: '1 项', delta: '-2' },
  { stage: '起诉条件', before: '4/6 通过', after: '5/6 通过', delta: '+1' },
]
