import type { InboxRow, InboxSourceTab } from './types'

/**
 * 收件箱页常量。
 *
 * 来源档位的值是后端 source_type 多值串（逗号分隔，list_messages 已支持多值）。
 * 顺序按「律师每天真正要看的优先级」排：法院送达在最前（有开庭/举证期限，
 * 漏了要担责），材料包最后（本身不进收件箱也该在材料预处理页）。
 */
export const INBOX_SOURCE_TABS: InboxSourceTab[] = [
  { key: 'all', label: '全部' },
  { key: 'court_inbox', label: '一张网' },
  { key: 'imap', label: '邮箱' },
  { key: 'court_sms', label: '法院短信' },
  { key: 'manual_upload,client_upload', label: '材料包' },
]

/** source_type → 中文来源标签（行内小徽章用；未知来源回原位展示原值） */
export const SOURCE_LABEL: Record<string, string> = {
  court_inbox: '一张网',
  imap: '邮箱',
  court_sms: '法院短信',
  court_schedule: '开庭排期',
  manual_upload: '材料包',
  client_upload: '客户上传',
}

/** source_type → 徽章配色（法院类用醒目色，其余中性） */
export const SOURCE_BADGE: Record<string, string> = {
  court_inbox: 'border-status-blue/30 bg-status-blue-bg text-status-blue',
  court_sms: 'border-status-blue/30 bg-status-blue-bg text-status-blue',
  court_schedule: 'border-status-blue/30 bg-status-blue-bg text-status-blue',
  manual_upload: 'border-border bg-secondary text-secondary-foreground',
  client_upload: 'border-border bg-secondary text-secondary-foreground',
  imap: 'border-border bg-secondary text-secondary-foreground',
}

/** 时间分组：今天 / 昨天 / 本周 / 更早（分组标题文案） */
export const TIME_GROUP_LABEL = {
  today: '今天',
  yesterday: '昨天',
  week: '本周',
  earlier: '更早',
} as const

/** 已读态在列表里的视觉：未读行左侧色条 + 主题加粗 */
export const UNREAD_ACCENT = 'bg-status-blue'

/** 空态文案（按筛选条件不同给不同提示，避免「收件箱是空的」误导） */
export function emptyHint(opts: { unreadOnly: boolean; search: string; allEmpty: boolean }): string {
  if (opts.search.trim()) return `没有匹配「${opts.search.trim()}」的消息`
  if (opts.unreadOnly) return '没有未读消息'
  if (opts.allEmpty) return '收件箱是空的'
  return '这一分类下暂无消息'
}

/** 行内副标题：发送人 + 来源。法院消息的发件人常带承办法官，形如「某某人民法院（张某某）」，
 *  原样展示即可——who 与 source 相同（邮箱来源常见）时去重，避免「A · A」。 */
export function rowSubtitle(row: InboxRow): string {
  const who = row.sender?.trim()
  const source = row.source_name?.trim()
  if (who && source && who !== source) return `${who} · ${source}`
  return who || source || ''
}
