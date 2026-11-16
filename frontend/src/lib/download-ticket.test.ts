/**
 * 下载票据助手（安全审计 M-2）单测。
 *
 * 背景：后端不再接受 `?token=<JWT>`——完整 JWT 会落进 nginx access log /
 * 浏览器历史 / Referer 头，拿到即等于拿到身份。改成换 60 秒一次性票据。
 *
 * 三件事必须锁死，因为错法都是「静默的」：
 * - `appendTicket` 拼错分隔符 → 下载 401，用户只看到「下载失败」；
 * - `stripTicket` 删不干净 → **票据进日志**（安全审计要防的正是这个）；
 * - `withDownloadTicket` 换票失败必须**返回原 url 而不是抛**：抛出去会让
 *   `<a href>` 直接拿不到值，比让后端按 403 处理更难定位。
 *
 * `stripTicket` 的正则是 `([?&])ticket=[^&]*(&|$)` + `tail ? lead : ''`：
 * 票据在中间时保留前导 `?`/`&`，在末尾时连前导一起删（否则会留下 `?` 或 `&`
 * 这种尾巴，拼回去就是坏 URL）。这三个位置（首/中/尾）各测一次。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())

vi.mock('./api', () => ({
  api: { post },
}))

import { appendTicket, stripTicket, withDownloadTicket } from './download-ticket'

/** ky ResponsePromise 形状桩 */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function fail(error: Error) {
  const p = Promise.reject(error)
  p.catch(() => {})
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('appendTicket', () => {
  it('URL 没有 query 时用 ? 起头', () => {
    expect(appendTicket('/api/v1/files/7/download', 'abc')).toBe('/api/v1/files/7/download?ticket=abc')
  })

  it('URL 已有 query 时用 & 追加（不能出现第二个 ?）', () => {
    expect(appendTicket('/api/v1/files/7/download?v=2', 'abc')).toBe('/api/v1/files/7/download?v=2&ticket=abc')
  })

  it('票据做 encodeURIComponent（票据里出现过 +/= 时不能破坏 query 解析）', () => {
    expect(appendTicket('/x', 'a+b/c=')).toBe('/x?ticket=a%2Bb%2Fc%3D')
  })

  it('空票据原样返回 url：宁可不带票让后端 403，也不拼出 ?ticket= 这种坏 URL', () => {
    expect(appendTicket('/x', '')).toBe('/x')
    expect(appendTicket('/x?v=2', '')).toBe('/x?v=2')
  })
})

describe('stripTicket', () => {
  it('票据在末尾：连前导分隔符一起删，不留 ? 或 & 尾巴', () => {
    expect(stripTicket('/x?a=1&ticket=abc')).toBe('/x?a=1')
    expect(stripTicket('/x?ticket=abc')).toBe('/x')
  })

  it('票据在中间：保留前导分隔符，后续参数不能丢', () => {
    expect(stripTicket('/x?ticket=abc&a=1')).toBe('/x?a=1')
    expect(stripTicket('/x?a=1&ticket=abc&b=2')).toBe('/x?a=1&b=2')
  })

  it('没有票据时原样返回', () => {
    expect(stripTicket('/x?a=1')).toBe('/x?a=1')
    expect(stripTicket('/x')).toBe('/x')
  })
})

describe('withDownloadTicket', () => {
  it('换取成功时拼上票据，resource 截到 200 字（后端审计字段有长度约束）', async () => {
    post.mockReturnValue(respond({ ticket: 't-1' }))
    const long = '/api/v1/files/' + 'a'.repeat(300)
    const url = await withDownloadTicket(long)

    // 拼上去的是**完整** path（下载地址不能截断）：截断只作用于换票请求里的
    // resource 审计字段
    expect(url).toBe(`${long}?ticket=t-1`)
    expect(post).toHaveBeenCalledWith('download-ticket', { json: { resource: long.slice(0, 200) } })
  })

  it('未登录 / 接口异常时返回原始 url，不抛', async () => {
    post.mockReturnValue(fail(new Error('401')))
    // 抛出去的话 <a href> 直接拿不到值，用户连「点下载报错」都看不到
    await expect(withDownloadTicket('/api/v1/files/7')).resolves.toBe('/api/v1/files/7')
  })
})
