/**
 * workbench/api/memory 单测（node 环境）。
 *
 * 只断言请求怎么构造：路径落在 `/api/v1/agent/memory`，筛选参数是后端的
 * snake_case `contract_id`（写成 camelCase 后端当没传，会静默返回全量记忆）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const client = { prefix: opts?.prefix ?? '/api/v1', get: vi.fn() }
    clients.push(client)
    return client
  },
}))

import { listProjectNotes } from './memory'

function client(prefix: string) {
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('listProjectNotes', () => {
  it('GET agent/memory?contract_id=<合同id>，默认 limit=50', async () => {
    const rows = [
      {
        id: 'm1',
        content: '对方已同意分期',
        confirmed_at: '',
        confirmed_by: '',
        case_id: null,
        created_at: '2026-10-01T09:00:00',
      },
    ]
    const api = client('/api/v1/agent')
    api.get.mockReturnValue(respond(rows))

    await expect(listProjectNotes(42)).resolves.toEqual(rows)
    expect(api.get).toHaveBeenCalledWith('memory', { searchParams: { contract_id: 42, limit: 50 } })
  })

  it('limit 可覆盖（面板只要一屏的量）', async () => {
    const api = client('/api/v1/agent')
    api.get.mockReturnValue(respond([]))

    await expect(listProjectNotes(7, 5)).resolves.toEqual([])
    expect(api.get).toHaveBeenCalledWith('memory', { searchParams: { contract_id: 7, limit: 5 } })
  })
})
