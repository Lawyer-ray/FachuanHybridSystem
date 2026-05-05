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
