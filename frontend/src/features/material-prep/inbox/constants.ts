import type { InboxRow, InboxSourceFilter, InboxSourceTab } from './types'

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

// ── 同步按钮 ──────────────────────────────────────────────
//
// 同步按钮贴在来源筛选条最右端，作用于**当前选中的档位**——这是它必须待在
// 那一行的唯一理由。放在顶栏（一级阶段行）会和筛选状态脱节：用户选着「邮箱」
// 却不知道点顶栏的同步是同步全部还是邮箱，这个歧义一定会变成投诉。
//
// court_schedule（开庭排期）不出现在任何具体档位的同步目标里：日程没有
// 「拉一封新消息」的语义，继续靠后台定时跑。只有「全部」会连带带上它。

/** 同步目标：'all' 走 sync-all 接口，字符串数组走逐个来源接口，null 表示该档位不可同步 */
export type SyncTarget = 'all' | readonly string[] | null

export interface SyncSpec {
  /** 按钮文案里「同步」后面的部分；null 表示置灰且不可点（材料包） */
  label: string | null
  /** 同步哪些 source_type；'all' 表示全部来源 */
  target: SyncTarget
  /** 置灰时给用户看的原因 */
  disabledReason?: string
}

/**
 * 档位 → 同步目标。顺序与 INBOX_SOURCE_TABS 对齐。
 *
 * 「全部」用 sync-all 而不是逐个调用：后端已在其内部做了可见性收敛
 * （安全审计 IDOR 修复），前端逐个调等于重写一遍权限逻辑，还要 N 次请求。
 * 具体档位才逐个调——因为 sync-all 不支持按 source_type 过滤。
 */
export const INBOX_SYNC_SPEC: { [K in InboxSourceFilter]: SyncSpec } = {
  all: { label: '全部', target: 'all' },
  court_inbox: { label: '一张网', target: ['court_inbox'] },
  imap: { label: '邮箱', target: ['imap'] },
  court_sms: { label: '短信', target: ['court_sms'] },
  'manual_upload,client_upload': {
    label: null,
    target: null,
    disabledReason: '材料包无需同步',
  },
}
