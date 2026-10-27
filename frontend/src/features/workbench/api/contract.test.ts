/**
 * workbench/api/contract 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient（contracts / cases / reminders /
 * organization 四个客户端）；断言聚焦 listContractsPage 的查询参数组合
 * （slim 固定、筛选随行）、单合同与案件提醒的路径，以及律师只读列表。
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
  getContract,
  listCasesByContract,
  listContractsPage,
  listLawyers,
  listRemindersByCase,
} from './contract'

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

  it('listLawyers：GET organization/lawyers?slim=true（只要映射用的四个字段）', async () => {
    const api = client('/api/v1/organization')
    const rows = [{ id: 1, real_name: '李律师', phone: null, license_no: null, law_firm_name: '某律所' }]
    api.get.mockReturnValueOnce(respond(rows))
    await expect(listLawyers()).resolves.toBe(rows)
    // slim 省掉 500 人 ×2 个文件签 URL + 律所嵌套对象
    expect(api.get).toHaveBeenCalledWith('lawyers', { searchParams: { slim: 'true' } })
  })
})

describe('单合同与案件提醒', () => {
  it('getContract 走 contracts/{id}', async () => {
    client('/api/v1/contracts').get.mockReturnValue(respond({ id: 7 }))
    await getContract(7)
    expect(client('/api/v1/contracts').get).toHaveBeenCalledWith('contracts/7')
  })

  it('listRemindersByCase 把 case_id 转成字符串参数', async () => {
    client('/api/v1/reminders').get.mockReturnValue(respond([]))
    await listRemindersByCase(42)
    expect(client('/api/v1/reminders').get).toHaveBeenCalledWith('list', {
      searchParams: { case_id: '42' },
    })
  })
})
