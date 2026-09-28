import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import ky from 'ky'
import { errMessage } from './errors'

/**
 * errMessage 与 ky v2 真实行为的契约测试（起真实 HTTP 服务往返）。
 *
 * 背景：errMessage 依赖「ky 把 4xx/5xx 响应体预解析进 HTTPError.data」这一
 * ky v2 行为（HTTPError.js 的 TSDoc 有明确记载）。此前的依据只是仓库注释，
 * 这里用真实往返把它钉死——将来升级 ky 时若行为变化，这组用例会先红。
 */

let server: Server
let base = ''

beforeAll(async () => {
  server = createServer((req, res) => {
    const url = req.url ?? ''
    res.setHeader('content-type', 'application/json')
    if (url === '/json-message') {
      res.writeHead(400)
      res.end(JSON.stringify({ message: '后端业务消息' }))
    } else if (url === '/json-detail') {
      res.writeHead(401)
      res.end(JSON.stringify({ detail: 'DRF 风格 detail' }))
    } else if (url === '/json-error') {
      res.writeHead(400)
      res.end(JSON.stringify({ error: 'error 字段消息' }))
    } else if (url === '/text') {
      res.writeHead(400, { 'content-type': 'text/plain' })
      res.end('纯文本错误体')
    } else if (url === '/empty') {
      res.writeHead(400)
      res.end()
    } else if (url === '/ok') {
      res.writeHead(200)
      res.end(JSON.stringify({ ok: true }))
    } else if (url === '/hang') {
      // 故意不响应：给 TimeoutError 用例用
    } else {
      res.writeHead(404)
      res.end()
    }
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

afterAll(() => {
  server.closeAllConnections()
  return new Promise<void>((resolve) => server.close(() => resolve()))
})

/** 发一个注定失败的请求，把抛出的错误接住返回 */
async function catchOf(path: string, options?: Record<string, unknown>): Promise<Record<string, unknown>> {
  return ky
    .post(`${base}${path}`, { json: {}, retry: 0, ...options })
    .then(() => {
      throw new Error(`该路径本应失败：${path}`)
    })
    .catch((err: Record<string, unknown>) => err)
}

describe('errMessage：与 ky v2 HTTPError 的真实契约', () => {
  it('ky 把 JSON 响应体预解析进 error.data，message 字段优先', async () => {
    const err = await catchOf('/json-message')
    expect(err.name).toBe('HTTPError')
    expect(err.data).toEqual({ message: '后端业务消息' })
    expect(errMessage(err, 'fallback')).toBe('后端业务消息')
  })

  it('detail 字段兜底（Django / DRF 风格错误体）', async () => {
    const err = await catchOf('/json-detail')
    expect(errMessage(err, 'fallback')).toBe('DRF 风格 detail')
  })

  it('error 字段兜底', async () => {
    const err = await catchOf('/json-error')
    expect(errMessage(err, 'fallback')).toBe('error 字段消息')
  })

  it('纯文本响应体 → data 为文本原样透出', async () => {
    const err = await catchOf('/text')
    expect(errMessage(err, 'fallback')).toBe('纯文本错误体')
  })

  it('空响应体 → data undefined → 返回 fallback', async () => {
    const err = await catchOf('/empty')
    expect(err.data).toBeUndefined()
    expect(errMessage(err, 'fallback')).toBe('fallback')
  })

  it('TimeoutError → 超时文案（可定制）', async () => {
    const err = await catchOf('/hang', { timeout: 80 })
    expect(err.name).toBe('TimeoutError')
    expect(errMessage(err, 'fallback', '自定义超时文案')).toBe('自定义超时文案')
  })

  it('2xx 正常返回（确认测试服务器自身接线无误）', async () => {
    const data = await ky.post(`${base}/ok`, { json: {} }).json<{ ok: boolean }>()
    expect(data.ok).toBe(true)
  })
})
