/**
 * 本地日期的基础纯工具（跨 feature 通用：home / workbench / document-recognition 共用）。
 *
 * 统一口径：一律按**本地时区**计算，绝不用 toISOString（那是 UTC，东八区晚会差一天）；
 * 字符串解析一律 parseISO 而非 new Date（后者对 date-only / naive 串按 UTC 零点解析会偏移）。
 */

import { parseISO } from 'date-fns'

/** 补零：3 → '03' */
export function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** 本地时区的 YYYY-MM-DD（dateKey：日历格、提醒到期日等按天归组的键） */
export function dateKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/** 今天（本地）的 dateKey */
export function todayKey(now: Date = new Date()): string {
  return dateKey(now)
}

/** ISO（含时区偏移或 naive）→ datetime-local 需要的本地 "YYYY-MM-DDTHH:mm"。
 *  空值 / 解析失败返回 ''（输入框显示空，与旧运行时行为一致）。 */
export function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = parseISO(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
