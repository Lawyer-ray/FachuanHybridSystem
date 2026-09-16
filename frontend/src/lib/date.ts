/**
 * 日期格式化工具 — 统一使用 UTC+8 (Asia/Shanghai)
 */

const TZ = 'Asia/Shanghai'

/**
 * 格式化为 YYYY-MM-DD HH:mm
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      timeZone: TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/**
 * 格式化为 YYYY-MM-DD
 */
export function formatDateOnly(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      timeZone: TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}

/**
 * 相对时间格式化
 * - 今天：HH:mm
 * - 今年：MM-DD HH:mm
 * - 跨年：YYYY-MM-DD
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
    }
    const isThisYear = d.getFullYear() === now.getFullYear()
    if (isThisYear) {
      return d.toLocaleDateString('zh-CN', {
        timeZone: TZ,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    }
    return d.toLocaleDateString('zh-CN', {
      timeZone: TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}

/**
 * 格式化为 MM-DD（短日期）
 */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      timeZone: TZ,
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}
