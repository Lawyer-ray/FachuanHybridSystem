/**
 * 展示层时间格式化（跨 feature 通用：home 收件箱 / material-prep 材料卡共用）。
 *
 * 口径：今天 / 昨天 → 「今天 HH:mm」；更早按调用方选格式（中文月日或 MM-dd）。
 * 解析失败回 fallback（默认 ''），不抛错——列表里一条脏数据不该炸整屏。
 */

import { parseISO } from 'date-fns'

import { pad2 } from '@/lib/date'

/** 非今天/昨天的日期用哪种格式：cn = 「9 月 17 日」，md = 「09-17」 */
export type FriendlyTimeElseFormat = 'cn' | 'md'

export interface FriendlyTimeOptions {
  /** 解析失败时的返回值（默认 ''） */
  fallback?: string
  /** 更早日期的格式，默认 'cn' */
  else?: FriendlyTimeElseFormat
}

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

/** 今天/昨天 → HH:mm（「今天 09:30」）；其余 → cn 格式「9 月 17 日」或 md 格式「09-17」 */
export function friendlyTime(iso: string, opts: FriendlyTimeOptions = {}): string {
  const fallback = opts.fallback ?? ''
  const elseFmt = opts.else ?? 'cn'
  try {
    const d = parseISO(iso)
    if (Number.isNaN(d.getTime())) return fallback
    const now = new Date()
    const yesterday = new Date(now)
    yesterday.setDate(now.getDate() - 1)
    const hhmm = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
    if (sameDay(d, now)) return `今天 ${hhmm}`
    if (sameDay(d, yesterday)) return `昨天 ${hhmm}`
    return elseFmt === 'md'
      ? `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
      : `${d.getMonth() + 1} 月 ${d.getDate()} 日`
  } catch {
    // parseISO 对非字符串入参抛 TypeError；签名虽是 string，防御运行时脏数据
    return fallback
  }
}
