/**
 * workbench/api/memory 单测（node 环境）。
 *
 * 只断言请求怎么构造：路径落在 `/api/v1/agent/memory`，筛选参数是后端的
 * snake_case `contract_id`（写成 camelCase 后端当没传，会静默返回全量记忆）；
 * 分页用 `limit`+`offset`；确认走 `/{id}/confirm` 且**不改写时不传 content**。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const client = { prefix: opts?.prefix ?? '/api/v1', get: vi.fn(), post: vi.fn() }
    clients.push(client)
    return client
  },
}))

import { confirmProjectNote, listProjectNotes } from './memory'

function client(prefix: string) {
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 'm1',
    content: '对方已同意分期',
    confirmed_at: '',
    confirmed_by: '',
    case_id: null,
    created_at: '2026-10-01T09:00:00',
    is_superseded: false,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('listProjectNotes', () => {
  it('GET agent/memory?contract_id=<合同id>&limit=50&offset=0（首屏第一页）', async () => {
    const rows = [row()]
    const api = client('/api/v1/agent')
    api.get.mockReturnValue(respond(rows))

    await expect(listProjectNotes(42)).resolves.toEqual(rows)
    expect(api.get).toHaveBeenCalledWith('memory', {
      searchParams: { contract_id: 42, limit: 50, offset: 0 },
    })
  })

  it('offset 可覆盖：加载更多按 50 步进往后再取一页', async () => {
    const api = client('/api/v1/agent')
    api.get.mockReturnValue(respond([]))

    await expect(listProjectNotes(7, { offset: 50 })).resolves.toEqual([])
    expect(api.get).toHaveBeenCalledWith('memory', {
      searchParams: { contract_id: 7, limit: 50, offset: 50 },
    })
  })

  it('limit 可覆盖（面板只要一屏的量时）', async () => {
    const api = client('/api/v1/agent')
    api.get.mockReturnValue(respond([]))

    await expect(listProjectNotes(7, { limit: 5 })).resolves.toEqual([])
    expect(api.get).toHaveBeenCalledWith('memory', {
      searchParams: { contract_id: 7, limit: 5, offset: 0 },
    })
  })
})

describe('confirmProjectNote', () => {
  it('POST agent/memory/<id>/confirm；不改写时 body 是空对象（不传 content）', async () => {
    const confirmed = row({ id: 'm-1', confirmed_at: '2026-10-02T10:00:00', confirmed_by: '王律师' })
    const api = client('/api/v1/agent')
    api.post.mockReturnValue(respond(confirmed))

    await expect(confirmProjectNote('m-1')).resolves.toEqual(confirmed)
    expect(api.post).toHaveBeenCalledWith('memory/m-1/confirm', { json: {} })
  })

  it('改写时带 content（律师说得更准时以新文本为准）', async () => {
    const api = client('/api/v1/agent')
    api.post.mockReturnValue(respond(row({ id: 'm-1', content: '对方已同意分三期，底线 80 万' })))

    await confirmProjectNote('m-1', '对方已同意分三期，底线 80 万')
    expect(api.post).toHaveBeenCalledWith('memory/m-1/confirm', {
      json: { content: '对方已同意分三期，底线 80 万' },
    })
  })
})
