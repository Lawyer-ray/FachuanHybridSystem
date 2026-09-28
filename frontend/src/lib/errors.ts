/**
 * 从 ky 的错误里取后端可读文案（跨 feature 通用，auth / home 共用）。
 * ky 的 HTTPError 已把响应体解析进 error.data（JSON 时为对象），后端错误体统一
 * { code, message, error, errors }，所以优先取 data.message / data.error。
 * 超时单独认（ky 抛 TimeoutError，没有 data），否则用户只会看到一句笼统失败。
 */
export function errMessage(e: unknown, fallback: string, timeoutMessage = '请求超时，请稍后重试'): string {
  if (!e || typeof e !== 'object') return fallback
  const name = (e as { name?: unknown }).name
  if (name === 'TimeoutError') return timeoutMessage
  const data = (e as { data?: unknown }).data
  if (data && typeof data === 'object') {
    const d = data as { message?: unknown; error?: unknown; detail?: unknown }
    if (typeof d.message === 'string' && d.message) return d.message
    if (typeof d.error === 'string' && d.error) return d.error
    // Django / DRF 风格的错误体（如 simplejwt 的 { detail: ... }）
    if (typeof d.detail === 'string' && d.detail) return d.detail
  }
  if (typeof data === 'string' && data) return data
  const msg = (e as { message?: unknown }).message
  return typeof msg === 'string' && msg ? msg : fallback
}
