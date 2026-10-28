import type { InboxRow } from './types'

/**
 * 收件箱列表的纯领域逻辑（可单测，不依赖 React）。
 *
 * 时间分组刻意按「自然日」而不是「N 小时前」：律师看收件箱时脑子里是
 * 「法院昨天发的」而不是「28 小时前发的」。跨天误差在收件箱场景里是噪音。
 */

export type TimeGroupKey = 'today' | 'yesterday' | 'week' | 'earlier'

export interface TimeGroup {
  key: TimeGroupKey
  rows: InboxRow[]
}

/** 取 ISO 时间的本地日期零点（便于按天比较） */
function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/**
 * 把列表按收到时间分组：今天 / 昨天 / 本周（近 7 日）/ 更早。
 *
 * 保持后端给的倒序，组内不再排序（后端已按 received_at 倒序，重排只会引入
 * 不一致的边界行为）。解析失败的行归「更早」——宁可埋在最下面，也不要
 * 因一条脏数据让整页分组崩掉。
 */
export function groupByTime(rows: InboxRow[], now: Date = new Date()): TimeGroup[] {
  const today = startOfDay(now)
  const dayMs = 86_400_000
  const yesterday = today - dayMs
  const weekStart = today - 6 * dayMs

  const buckets: Record<TimeGroupKey, InboxRow[]> = { today: [], yesterday: [], week: [], earlier: [] }

  for (const row of rows) {
    const t = new Date(row.received_at).getTime()
    if (Number.isNaN(t)) {
      buckets.earlier.push(row)
      continue
    }
    const day = startOfDay(new Date(t))
    if (day >= today) buckets.today.push(row)
    else if (day >= yesterday) buckets.yesterday.push(row)
    else if (day >= weekStart) buckets.week.push(row)
    else buckets.earlier.push(row)
  }

  return (['today', 'yesterday', 'week', 'earlier'] as const)
    .filter((k) => buckets[k].length > 0)
    .map((k) => ({ key: k, rows: buckets[k] }))
}

/**
 * 本地过滤：已读/未读与关键字。
 *
 * 后端已支持 unread_only 与 search 参数（pg_trgm 索引），本函数**只**在
 * 「已取回的这批数据上做二次筛」时使用（如标记已读后即时隐藏）。
 * 不要把全库搜索做成前端 filter——limit 之外的消息永远搜不到。
 */
export function filterRows(
  rows: InboxRow[],
  opts: { unreadOnly?: boolean; keyword?: string },
): InboxRow[] {
  const kw = opts.keyword?.trim().toLowerCase()
  return rows.filter((r) => {
    if (opts.unreadOnly && r.is_read) return false
    if (!kw) return true
    return (
      r.subject?.toLowerCase().includes(kw) ||
      r.sender?.toLowerCase().includes(kw) ||
      r.source_name?.toLowerCase().includes(kw)
    )
  })
}

/** 未读条数（顶栏徽章用） */
export function countUnread(rows: InboxRow[]): number {
  return rows.reduce((n, r) => (r.is_read ? n : n + 1), 0)
}
