/**
 * 从 ky 的错误里取后端 message。
 * ky 的 HTTPError 已把响应体解析进 error.data（JSON 时为对象），后端错误体统一
 * { code, message, error, errors }，所以优先取 data.message / data.error。
 * 超时单独认（ky 抛 TimeoutError，没有 data），否则用户只会看到一句笼统失败。
 */
export function errMessage(e: unknown, fallback: string): string {
  if (!e || typeof e !== 'object') return fallback
  const name = (e as { name?: unknown }).name
  if (name === 'TimeoutError') return '请求超时——后端转换耗时过久或服务无响应，可稍后重试'
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
