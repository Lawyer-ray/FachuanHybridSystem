/**
 * client-upload api 层单测（node 环境）。
 *
 * 两个关注点：
 * 1. token 走 `X-Upload-Token` 头而不是 URL —— 公开链接的 token 不能进访问日志；
 * 2. 上传走原生 XHR（ky/fetch 拿不到上传进度），失败必须给出可读中文，
 *    而不是浏览器那句空白/英文。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { client, get } = vi.hoisted(() => {
  const get = vi.fn()
  const client = { get, post: vi.fn() }
  return { client, get }
})

vi.mock('@/lib/api', () => ({
  API_BASE_URL: 'https://api.test',
  createApiClient: () => client,
}))

import { getLinkInfo, listUploadedFiles, uploadFiles } from './api'

beforeEach(() => {
  vi.clearAllMocks()
})

const json = <T,>(value: T) => ({ json: () => Promise.resolve(value) })

describe('getLinkInfo / listUploadedFiles', () => {
  it('token 放 X-Upload-Token 头，不进 query', async () => {
    get.mockReturnValue(json({ title: '材料收取', state: 'open' }))
    const info = await getLinkInfo('tok-1')
    expect(info.title).toBe('材料收取')
    expect(get).toHaveBeenCalledWith('material-link', { headers: { 'X-Upload-Token': 'tok-1' } })
  })

  it('已传文件列表同样用头传 token', async () => {
    get.mockReturnValue(json([{ filename: 'a.pdf', size: 10 }]))
    await expect(listUploadedFiles('tok-2')).resolves.toEqual([{ filename: 'a.pdf', size: 10 }])
    expect(get).toHaveBeenCalledWith('material-link/files', { headers: { 'X-Upload-Token': 'tok-2' } })
  })
})

/**
 * 用一个可编程的假 XHR 替身驱动 uploadFiles：真实 XMLHttpRequest 在 node 下不可用，
 * 而这里要测的正是「onload/onerror/ontimeout 各分支给出什么」。只实现被测代码
 * 实际调用的成员：open / setRequestHeader / send / upload.onprogress / 事件槽。
 */
class FakeXhr {
  static last: FakeXhr
  method = ''
  url = ''
  headers: Record<string, string> = {}
  timeout = 0
  status = 0
  responseText = ''
  body: FormData | null = null
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null

  constructor() {
    FakeXhr.last = this
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v
  }
  send(body: FormData) {
    this.body = body
  }
}

const file = (name: string) => new File(['x'], name, { type: 'application/pdf' })

describe('uploadFiles', () => {
  beforeEach(() => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
  })

  it('POST 到公开端点，token 头 + 多文件 + 备注进 FormData', async () => {
    const p = uploadFiles('tok-3', [file('a.pdf'), file('b.pdf')], ' 第一批证据 ')

    const xhr = FakeXhr.last
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('https://api.test/public/material-link/files')
    expect(xhr.headers['X-Upload-Token']).toBe('tok-3')
    expect(xhr.timeout).toBe(300_000)
    const names = (xhr.body as FormData).getAll('files').map((f) => (f as File).name)
    expect(names).toEqual(['a.pdf', 'b.pdf'])
    expect((xhr.body as FormData).get('remark')).toBe('第一批证据')

    xhr.status = 200
    xhr.responseText = JSON.stringify({ files: [{ filename: 'a.pdf' }] })
    xhr.onload?.()
    await expect(p).resolves.toEqual({ files: [{ filename: 'a.pdf' }] })
  })

  it('备注全是空白时不带 remark 字段', () => {
    void uploadFiles('t', [file('a.pdf')], '   ')
    expect((FakeXhr.last.body as FormData).get('remark')).toBeNull()
  })

  it('进度回调按四舍五入上报百分比，不可计算长度时不上报', () => {
    const onProgress = vi.fn()
    void uploadFiles('t', [file('a.pdf')], '', onProgress)

    const upload = FakeXhr.last.upload
    upload.onprogress?.({ lengthComputable: true, loaded: 33, total: 100 })
    upload.onprogress?.({ lengthComputable: false, loaded: 50, total: 100 })
    expect(onProgress).toHaveBeenCalledTimes(1)
    expect(onProgress).toHaveBeenCalledWith(33)
  })

  it('2xx：解析 JSON 为结果', async () => {
    const p = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 201
    FakeXhr.last.responseText = JSON.stringify({ files: [] })
    FakeXhr.last.onload?.()
    await expect(p).resolves.toEqual({ files: [] })
  })

  it('2xx 但响应不是 JSON：给出「服务返回异常」而不是抛原始 JSON 错误', async () => {
    const p = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 200
    FakeXhr.last.responseText = '<html>gateway</html>'
    FakeXhr.last.onload?.()
    await expect(p).rejects.toThrow('服务返回异常，请重试')
  })

  it('4xx/5xx：优先取错误信封里的 message', async () => {
    const p = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 413
    FakeXhr.last.responseText = JSON.stringify({ success: false, message: '单个文件超过 50MB' })
    FakeXhr.last.onload?.()
    await expect(p).rejects.toThrow('单个文件超过 50MB')
  })

  it('错误信封没 message 时退到 detail', async () => {
    const p = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 403
    FakeXhr.last.responseText = JSON.stringify({ detail: '链接已失效' })
    FakeXhr.last.onload?.()
    await expect(p).rejects.toThrow('链接已失效')
  })

  it('错误体不是 JSON 或 message 非字符串：退到带状态码的兜底文案', async () => {
    const p1 = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 500
    FakeXhr.last.responseText = 'Internal Server Error'
    FakeXhr.last.onload?.()
    await expect(p1).rejects.toThrow('上传失败（500），请重试')

    const p2 = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.status = 400
    FakeXhr.last.responseText = JSON.stringify({ message: 42 })
    FakeXhr.last.onload?.()
    await expect(p2).rejects.toThrow('上传失败（400），请重试')
  })

  it('网络错误 / 超时各自有独立文案', async () => {
    const p1 = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.onerror?.()
    await expect(p1).rejects.toThrow('网络错误，请检查网络后重试')

    const p2 = uploadFiles('t', [file('a.pdf')], '')
    FakeXhr.last.ontimeout?.()
    await expect(p2).rejects.toThrow('上传超时，请重试')
  })
})
