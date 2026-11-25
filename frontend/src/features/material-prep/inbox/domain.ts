import type { InboxAttachment, InboxRow } from './types'

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

// ── 附件：名称 / 类型 / 页数（列表小样与预览弹窗共用的口径） ──────────────
//
// 这三件放在纯函数里而不是散在组件中：行内小样、抽屉附件清单、预览弹窗三处都要
// 用同一套判定，各写一份必然漂移（例如「.PDF 大写后缀」只有一处认得出来）。

/**
 * 附件展示名：用户改过的名字优先，其次原始名，最后兜底名。
 *
 * 后端已经把 `filename` 归一成「一定有值」（缺失时给 `attachment_N`），但
 * `custom_filename` 才是用户在收件箱里点过重命名后的真名——卷宗归档、材料包
 * 命名都认它，列表里也必须认，否则「我明明改过名，这里还是 1153_001.pdf」。
 */
export function attachmentDisplayName(att: InboxAttachment): string {
  const custom = att.custom_filename?.trim()
  if (custom) return custom
  return (att.original_filename || att.filename || '').trim() || '未命名附件'
}

/** 附件能怎么预览：PDF 走 pdf.js 分页，位图直接显示，其余只能下载 */
export type AttachmentKind = 'pdf' | 'image' | 'other'

const IMAGE_CONTENT_TYPES = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
  'image/gif',
  'image/bmp',
  'image/tiff',
])
const IMAGE_SUFFIXES = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff']

/**
 * 预览类型判定：与后端 `attachment_thumbnail_service.thumbnail_kind` 同口径。
 *
 * 前后端口径必须一致：后端说「能出缩略图」而前端说「不能预览」，用户会看到
 * 有图却点不开；反过来则是点开一片空白。
 */
export function attachmentKind(att: InboxAttachment): AttachmentKind {
  const contentType = (att.content_type || '').split(';')[0]?.trim().toLowerCase() ?? ''
  const name = (att.filename || att.original_filename || '').toLowerCase()
  if (contentType.includes('pdf') || name.endsWith('.pdf')) return 'pdf'
  if (IMAGE_CONTENT_TYPES.has(contentType) || IMAGE_SUFFIXES.some((s) => name.endsWith(s))) return 'image'
  return 'other'
}

/** 页数文案：PDF 有页数就写「12 页」，其余不写（图片恒 1 页说「1 页」是噪音） */
export function attachmentPagesLabel(att: InboxAttachment): string {
  const pages = att.page_count ?? 0
  if (attachmentKind(att) !== 'pdf' || pages <= 0) return ''
  return `${pages} 页`
}
