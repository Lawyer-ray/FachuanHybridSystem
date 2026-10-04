/**
 * document-recognition/api 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient；断言聚焦：recognizeFile 的
 * multipart 组装与上传超时档位、confirm/revoke 的路径拼装、
 * searchCasesForBinding 的查询参数与 signal 透传。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const client = {
      prefix: opts?.prefix ?? '/api/v1',
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    }
    clients.push(client)
    return client
  },
}))

import {
  bindTask,
  confirmDates,
  getTask,
  recognizeFile,
  revokeDate,
  searchCasesForBinding,
} from './api'

function drClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/document-recognition')
  if (!c) throw new Error('document-recognition 客户端未创建')
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('提交与查询', () => {
  it('recognizeFile：file 进 FormData，POST court-document/recognize，超时走上传档位', async () => {
    const api = drClient()
    api.post.mockReturnValueOnce(respond({ task_id: 11 }))
    const file = new File(['pdf-bytes'], '传票.pdf', { type: 'application/pdf' })

    await expect(recognizeFile(file)).resolves.toEqual({ task_id: 11 })

    const [path, opts] = api.post.mock.calls[0]! as [string, { body: FormData; timeout: number }]
    expect(path).toBe('court-document/recognize')
    expect(opts.body.get('file')).toBeInstanceOf(File)
    expect((opts.body.get('file') as File).name).toBe('传票.pdf')
    expect(opts.timeout).toBe(300_000)
  })

  it('getTask：GET court-document/task/:id 直通', async () => {
    const api = drClient()
    const task = { task_id: 11, status: 'processing', date_candidates: [] }
    api.get.mockReturnValueOnce(respond(task))
    await expect(getTask(11)).resolves.toBe(task)
    expect(api.get).toHaveBeenCalledWith('court-document/task/11')
  })
})

describe('绑定与日期确认', () => {
  it('bindTask：POST task/:id/bind 传 case_id', async () => {
    const api = drClient()
    api.post.mockReturnValueOnce(respond({}))
    await bindTask(11, 42)
    expect(api.post).toHaveBeenCalledWith('court-document/task/11/bind', { json: { case_id: 42 } })
  })

  it('confirmDates：items 进 json body，响应直通', async () => {
    const api = drClient()
    const out = { results: [{ candidate_id: 1, status: 'success', message: 'ok' }] }
    api.post.mockReturnValueOnce(respond(out))
    const items = [{ candidate_id: 1, action: 'confirm' as const, due_at: '2026-10-01T09:30', reminder_type: 'hearing' }]
    await expect(confirmDates(11, items)).resolves.toBe(out)
    expect(api.post).toHaveBeenCalledWith('court-document/task/11/dates/confirm', { json: { items } })
  })

  it('revokeDate：POST task/:id/dates/:cid/revoke', async () => {
    const api = drClient()
    api.post.mockReturnValueOnce(respond({}))
    await revokeDate(11, 5)
    expect(api.post).toHaveBeenCalledWith('court-document/task/11/dates/5/revoke')
  })
})

describe('searchCasesForBinding', () => {
  it('默认 limit=10，signal 透传', async () => {
    const api = drClient()
    const rows = [{ id: 1, name: '张三案', case_number: '(2026)粤01民初1号' }]
    api.get.mockReturnValueOnce(respond(rows))
    const ac = new AbortController()

    await expect(searchCasesForBinding('张三', { signal: ac.signal })).resolves.toBe(rows)
    expect(api.get).toHaveBeenCalledWith('court-document/search-cases', {
      searchParams: { q: '张三', limit: '10' },
      signal: ac.signal,
    })
  })

  it('自定义 limit 覆盖默认；不传 signal 为 undefined', async () => {
    const api = drClient()
    api.get.mockReturnValue(respond([]))
    await searchCasesForBinding('李四', { limit: 5 })
    expect(api.get).toHaveBeenCalledWith('court-document/search-cases', {
      searchParams: { q: '李四', limit: '5' },
      signal: undefined,
    })
    await searchCasesForBinding('')
    expect(api.get).toHaveBeenLastCalledWith('court-document/search-cases', {
      searchParams: { q: '', limit: '10' },
      signal: undefined,
    })
  })
})
