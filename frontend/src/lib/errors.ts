import { HTTPError } from 'ky'

/**
 * 从 ky 的错误里取后端可读文案（跨 feature 通用，auth / home 共用）。
 *
 * ky v2 会把 4xx/5xx 响应体预解析进 HTTPError.data（JSON 按 Content-Type 解析，
 * 见 ky HTTPError.js 的 TSDoc；真实往返契约见 errors.test.ts）。后端错误体统一
 * { code, message, error, errors } 或 Django/DRF 的 { detail }，依次取。
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
    if (typeof d.detail === 'string' && d.detail) return d.detail
  }
  if (typeof data === 'string' && data) return data
  // HTTPError 自身的 e.message 是英文技术描述（"Request failed with status code …"），
  // 对用户没有信息量：data 不可用时直接回 fallback。网络类错误（NetworkError 等）
  // 没有 data，其 e.message（如 "fetch failed"）同样没信息量，统一 fallback。
  if (e instanceof HTTPError) return fallback
  const msg = (e as { message?: unknown }).message
  return typeof msg === 'string' && msg ? msg : fallback
}
