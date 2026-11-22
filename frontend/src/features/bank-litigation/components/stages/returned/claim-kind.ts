/**
 * 归案日志的筛选口径 —— 把邮件行上的「处理结果」文案翻成三分法。
 *
 * 为什么不用后端字段：这一屏的邮件行是演示数据，动作文案本身就是结果；
 * 筛选条（全部 / 自动归案 / 待人工 / 已标记无关）只认这三种口径，
 * 所以收敛成一个纯函数，面板与抽屉共用以保证两边判定一致。
 */

import type { ClaimFilter, ReturnedMailRow } from '../../demo-data'

/** 归案日志里一封邮件的筛选口径 */
export type ClaimKind = 'auto' | 'manual' | 'ignored'

export function claimKindOf(action: string): ClaimKind {
  if (action.startsWith('已标记无关')) return 'ignored'
  if (action.startsWith('已自动') || action.startsWith('已归案')) return 'auto'
  return 'manual'
}

/**
 * 筛选条上的名字 → 三分法口径。
 *
 * 「全部」不对应任何一个口径，回 `null` 表示**不过滤**。
 * 调用方必须把 `null` 当成「全匹配」而不是「匹配 unknown」，否则「全部」会是 0 条。
 */
export function filterKindOf(f: ClaimFilter): ClaimKind | null {
  if (f === '全部') return null
  if (f === '自动归案') return 'auto'
  if (f === '待人工') return 'manual'
  return 'ignored'
}

/**
 * 把「已标记无关」套到邮件行上。
 *
 * 面板顶部的统计格与归案卡片的列表必须用同一份变换 ——
 * 各自铺一版的话，会出现「顶部说 3 封待人工、卡片里只剩 2 封」这种口径漂移。
 */
export function mapIgnored(rows: ReturnedMailRow[], ignored: Set<string>): ReturnedMailRow[] {
  return rows.map((m) => (ignored.has(m.subject) ? { ...m, action: '已标记无关' } : m))
}
