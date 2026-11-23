/**
 * 演示数据 · G3. ③ 缺件
 *
 * 缺什么、怎么催、客户补回来了什么。
 */

// ───────────────────────── ③ 缺件 · 补件清单 ─────────────────────────

export interface GapNoticeRow {
  item: string
  reason: string
  severity: 'blocker' | 'normal'
  channel: string
  sentAt: string
  status: 'waiting' | 'received' | 'pending'
  reply: string
}

export const DEMO_GAP_NOTICES: GapNoticeRow[] = [
  { item: '催收记录（2025 年后）', reason: '现有催收记录止于 2025-06，缺最近 12 个月，影响诉讼时效举证', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'received', reply: '客户已于 10-30 补传 2 份' },
  { item: '借款人最新联系方式', reason: '合同留存电话已停用，送达地址需更新', severity: 'normal', channel: '微信', sentAt: '10-28 14:02', status: 'received', reply: '客户提供新手机号与现住址' },
  { item: '抵押物权属证明', reason: '合同约定抵押，但未见不动产权证复印件', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'waiting', reply: '—' },
  { item: '共同借款人身份证明', reason: '合同列明两位借款人，仅见一人身份证', severity: 'blocker', channel: '短信 + 邮件', sentAt: '10-28 14:02', status: 'waiting', reply: '—' },
  { item: '还款账户近半年流水', reason: '已有流水止于 2026-04，建议补至起诉前一月', severity: 'normal', channel: '邮件', sentAt: '10-30 09:15', status: 'pending', reply: '—' },
]

// ───────────────────────── ③ 缺件 · 客户补回的材料 ─────────────────────────

export interface GapReceivedRow {
  item: string
  fileName: string
  pages: number
  receivedAt: string
  recognized: boolean
  note: string
}

export const DEMO_GAP_RECEIVED: GapReceivedRow[] = [
  { item: '催收记录（2025 年后）', fileName: '催收记录_补充_2025Q3-Q4.pdf', pages: 6, receivedAt: '10-30 09:20', recognized: true, note: '识别到电话催收 7 次、上门 2 次' },
  { item: '借款人最新联系方式', fileName: '客户补充信息.txt', pages: 1, receivedAt: '10-30 09:22', recognized: true, note: '手机号 138****XXXX，现住址已更新' },
]

// ───────────────────────── ③ 缺件 · 催办话术模板 ─────────────────────────

export interface GapTemplateRow {
  severity: string
  title: string
  body: string
  channel: string
}

export const DEMO_GAP_TEMPLATES: GapTemplateRow[] = [
  { severity: '硬阻塞', title: '影响立案的缺件', body: '以下材料缺失将无法立案，请尽快补充：{list}', channel: '短信 + 邮件 + 微信' },
  { severity: '一般', title: '建议补充的材料', body: '以下材料建议补充，不影响先立案：{list}', channel: '邮件' },
  { severity: '催办', title: '补件催办提醒', body: '您还有 {n} 项材料未补齐，已超 {days} 天，请尽快处理', channel: '短信' },
  { severity: '回执', title: '已收妥确认', body: '您补交的 {n} 份材料已收到并归档，无需再重复提交', channel: '短信' },
]
