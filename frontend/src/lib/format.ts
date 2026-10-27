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

/** 字节档位（1024 进制）：B / KB / MB / GB */
const BYTE_UNITS = ['B', 'KB', 'MB', 'GB'] as const

/** 各档小数位：KB 及以下取整（「512KB」比「512.0KB」干净），MB / GB 保留一位 */
const BYTE_DECIMALS = [0, 0, 1, 1] as const

/**
 * 人类可读的文件大小。收敛前有 4 份手写实现，其中 2 份漏了 GB 档，
 * 大文件被显示成「512000.0MB」这种没法读的数。
 *
 * 口径（取 client-upload / ShareLinkPanel 两份的正确行为）：
 * - 1024 进制逐档进位，最高到 GB（再大也按 GB 显示，避免 TB 档在律师场景下无意义）；
 * - 小数位按档位定：B / KB 四舍五入到整数，MB / GB 保留 1 位；
 * - 与 ShareLinkPanel 一致，KB 档下限取 1（1~1023 字节都显示「1KB」），
 *   否则几百字节的小文件在「剩余容量」里显示成「0KB」看着像已用尽；
 * - 非法入参（负值 / NaN）回「0B」，不让脏数据把界面撑破。
 */
export function formatBytes(bytes: number, opts: { space?: boolean; decimals?: number } = {}): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return `0${opts.space ? ' ' : ''}B`
  // 逐档进位：先按 1024 缩到 <1024 再定档，避免 1024^4 以上写死一长串分支
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digitsOf = (u: number) => opts.decimals ?? BYTE_DECIMALS[u]
  // 四舍五入后可能满 1024 却还没升档（1.4KB 按 KB 取整 → 「1024B」），
  // 此时改为升一档重算，避免出现「1024B」「1024KB」这种读不成数的值
  let shown = Number(value.toFixed(digitsOf(unit)))
  if (shown >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit += 1
    shown = Number(value.toFixed(digitsOf(unit)))
  }
  // KB 档下限 1：几百字节显示成「0KB」会被误读为已用尽 / 文件为空
  if (unit === 1) shown = Math.max(1, shown)
  return `${shown.toFixed(digitsOf(unit))}${opts.space ? ' ' : ''}${BYTE_UNITS[unit]}`
}
