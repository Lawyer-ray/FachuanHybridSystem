/**
 * workbench/api 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient（contracts / cases / organization
 * 三个客户端）；断言聚焦 listContractsPage 的查询参数组合（slim 固定、
 * 筛选随行）与两个只读列表的路径。
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

import { listCasesByContract, listContractsPage, listLawyers } from './api'

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

describe('listContractsPage（slim 模式 + 筛选随行）', () => {
  it('只传 page：slim=true、page_size 默认 50，不带筛选键', async () => {
    const api = client('/api/v1/contracts')
    const page = { items: [], count: 0, page: 1, num_pages: 0, facets: {} }
    api.get.mockReturnValueOnce(respond(page))
    await expect(listContractsPage({ page: 1 })).resolves.toBe(page)
    expect(api.get).toHaveBeenCalledWith('contracts', {
      searchParams: { slim: 'true', page: '1', page_size: '50' },
    })
  })

  it('自定义 pageSize 与全部筛选（status/cat/fee/q）随行，键名映射到后端参数', async () => {
    const api = client('/api/v1/contracts')
    api.get.mockReturnValueOnce(respond({ items: [], count: 0, page: 2, num_pages: 0, facets: {} }))
    await listContractsPage({
      page: 2,
      pageSize: 20,
      status: 'active',
      cat: 'civil',
      fee: 'hourly',
      q: '张三',
    })
    expect(api.get).toHaveBeenCalledWith('contracts', {
      searchParams: {
        slim: 'true',
        page: '2',
        page_size: '20',
        status: 'active',
        case_type: 'civil',
        fee_mode: 'hourly',
        search: '张三',
      },
    })
  })
})

describe('案件与律师只读列表', () => {
  it('listCasesByContract：GET cases?contract_id=', async () => {
    const api = client('/api/v1/cases')
    const rows = [{ id: 7, name: '张三案' }]
    api.get.mockReturnValueOnce(respond(rows))
    await expect(listCasesByContract(15)).resolves.toBe(rows)
    expect(api.get).toHaveBeenCalledWith('cases', { searchParams: { contract_id: '15' } })
  })

  it('listLawyers：GET organization/lawyers 直通', async () => {
    const api = client('/api/v1/organization')
    const rows = [{ id: 1, name: '李律师' }]
    api.get.mockReturnValueOnce(respond(rows))
    await expect(listLawyers()).resolves.toBe(rows)
    expect(api.get).toHaveBeenCalledWith('lawyers')
  })
})
