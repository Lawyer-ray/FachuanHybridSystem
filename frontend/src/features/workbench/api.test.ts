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

  it('listLawyers：GET organization/lawyers?slim=true（只要映射用的四个字段）', async () => {
    const api = client('/api/v1/organization')
    const rows = [{ id: 1, real_name: '李律师', phone: null, license_no: null, law_firm_name: '某律所' }]
    api.get.mockReturnValueOnce(respond(rows))
    await expect(listLawyers()).resolves.toBe(rows)
    // slim 省掉 500 人 ×2 个文件签 URL + 律所嵌套对象
    expect(api.get).toHaveBeenCalledWith('lawyers', { searchParams: { slim: 'true' } })
  })
})

// ============ 文件夹接口契约（覆盖率补测） ============

import {
  copyFolderEntry,
  createFolderEntry,
  deleteFolderEntry,
  folderFileUrl,
  getCaseFolderBinding,
  getContract,
  listFolderEntries,
  listRemindersByCase,
  renameFolderEntry,
  uploadFolderFiles,
} from './api'

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

describe('文件夹接口：kind 选择客户端', () => {
  it('kind=case 走 cases 客户端', async () => {
    client('/api/v1/cases').get.mockReturnValue(respond({ folders: [], files: [] }))
    await listFolderEntries('case', 9, '')
    expect(client('/api/v1/cases').get).toHaveBeenCalledWith('9/folder-entries', { searchParams: {} })
  })

  it('kind=contract 走 contracts 客户端', async () => {
    client('/api/v1/contracts').get.mockReturnValue(respond({ folders: [], files: [] }))
    await listFolderEntries('contract', 9, 'dir')
    expect(client('/api/v1/contracts').get).toHaveBeenCalledWith('9/folder-entries', {
      searchParams: { subpath: 'dir' },
    })
  })

  it('空 subpath 不带 searchParams.subpath', async () => {
    client('/api/v1/cases').get.mockReturnValue(respond({ folders: [], files: [] }))
    await listFolderEntries('case', 1, '')
    const args = client('/api/v1/cases').get.mock.calls[0]!
    expect(args[1]).toEqual({ searchParams: {} })
  })
})

describe('文件夹接口：写操作路径', () => {
  it('createFolderEntry 走 folder-mkdir', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({ subpath: 'dir/new', name: 'new' }))
    await createFolderEntry('case', 1, 'dir', 'new')
    expect(client('/api/v1/cases').post).toHaveBeenCalledWith('1/folder-mkdir', {
      json: { subpath: 'dir', name: 'new' },
    })
  })

  it('renameFolderEntry 走 folder-rename', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({ subpath: 'dir/b', name: 'b' }))
    await renameFolderEntry('case', 1, 'dir/a', 'b')
    expect(client('/api/v1/cases').post).toHaveBeenCalledWith('1/folder-rename', {
      json: { subpath: 'dir/a', name: 'b' },
    })
  })

  it('copyFolderEntry 走 folder-copy', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({}))
    await copyFolderEntry('case', 1, 'dir/a.pdf', 'dest')
    expect(client('/api/v1/cases').post).toHaveBeenCalledWith('1/folder-copy', {
      json: { subpath: 'dir/a.pdf', dest_subpath: 'dest' },
    })
  })

  it('deleteFolderEntry 走 folder-delete（POST，语义是移入 _已删除）', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({}))
    await deleteFolderEntry('case', 1, 'dir/a.pdf')
    expect(client('/api/v1/cases').post).toHaveBeenCalledWith('1/folder-delete', {
      json: { subpath: 'dir/a.pdf' },
    })
  })
})

describe('文件夹接口：上传与预览直链', () => {
  it('uploadFolderFiles 传 timeout 且按 subpath 带参', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({ saved: [] }))
    const files = [new File(['x'], 'a.pdf')]
    await uploadFolderFiles('case', 1, 'dir', files)
    const [path, opts] = client('/api/v1/cases').post.mock.calls[0]!
    expect(path).toBe('1/folder-upload')
    expect(opts.searchParams).toEqual({ subpath: 'dir' })
    expect(opts.timeout).toBe(300_000)
  })

  it('空 subpath 上传不带 searchParams', async () => {
    client('/api/v1/cases').post.mockReturnValue(respond({ saved: [] }))
    await uploadFolderFiles('case', 1, '', [])
    const [, opts] = client('/api/v1/cases').post.mock.calls[0]!
    expect(opts.searchParams).toEqual({})
  })

  it('folderFileUrl 对 subpath 做 encodeURIComponent', () => {
    const url = folderFileUrl('case', 5, 'dir/a b.pdf')
    expect(url).toContain('/api/v1/cases/5/folder-file')
    expect(url).toContain('subpath=dir%2Fa%20b.pdf')
  })

  it('folderFileUrl 合同类走 contracts 段', () => {
    expect(folderFileUrl('contract', 9, 'x.pdf')).toContain('/api/v1/contracts/9/folder-file')
  })
})

describe('案件文件夹绑定', () => {
  it('getCaseFolderBinding 走 {id}/folder-binding', async () => {
    client('/api/v1/cases').get.mockReturnValue(respond(null))
    const r = await getCaseFolderBinding(3)
    expect(client('/api/v1/cases').get).toHaveBeenCalledWith('3/folder-binding')
    expect(r).toBeNull()
  })
})
