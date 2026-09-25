/**
 * 从 ky 的错误里取后端 message。
 * ky 的 HTTPError 已把响应体解析进 error.data（JSON 时为对象），后端错误体统一
 * { code, message, error, errors }，所以优先取 data.message / data.error。
 */
export function errMessage(e: unknown, fallback: string): string {
  if (!e || typeof e !== 'object') return fallback
  const data = (e as { data?: unknown }).data
  if (data && typeof data === 'object') {
    const d = data as { message?: unknown; error?: unknown }
    if (typeof d.message === 'string' && d.message) return d.message
    if (typeof d.error === 'string' && d.error) return d.error
  }
  if (typeof data === 'string' && data) return data
  const msg = (e as { message?: unknown }).message
  return typeof msg === 'string' && msg ? msg : fallback
}
