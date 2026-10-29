/**
 * workbench/api/folder 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient（cases 与合同文件夹两个客户端）；
 * 断言聚焦 folderApi(kind) 的客户端选择、写操作路径、上传超时与 subpath 口径，
 * 以及预览直链的 encodeURIComponent 与「另存为意图登记」（只登记、不发字节）。
 *
 * **合同侧客户端前缀是 `/api/v1/contracts`**：合同文件夹端点挂的是
 * `/{contract_id}/folder-entries`（没有第二个 contracts 段），与合同 CRUD 的
 * `/api/v1/contracts/contracts/...` 不同——这两条曾写成同一个客户端，导致
 * folder-entries 实测 404（curl 探活判定）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 桩客户端列表。**同前缀可能建两个实例**（合同 CRUD 的 `/api/v1/contracts` 与
 * 合同文件夹的 `/api/v1/contracts` 是分开建的两个客户端），所以按「调用顺序」
 * 记录、用 `clientAt(n)` 取，而不是按前缀查唯一实例。
 */
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
  copyFolderEntry,
  createFolderEntry,
  deleteFolderEntry,
  folderFileUrl,
  getCaseFolderBinding,
  listFolderEntries,
  registerFolderSaveAsIntent,
  renameFolderEntry,
  uploadFolderFiles,
} from './folder'

/** 按创建顺序取客户端：0 = contractsApi(CRUD)，1 = contractFolderApi(文件夹)，2 = casesApi */
function clientAt(index: number) {
  const c = clients[index]
  if (!c) throw new Error(`客户端 #${index} 未创建`)
  return c
}

/** 兼容旧断言：按前缀取第一个（cases 只有实例一个） */
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

// ============ 文件夹接口契约（覆盖率补测） ============

describe('文件夹接口：kind 选择客户端', () => {
  it('kind=case 走 cases 客户端', async () => {
    client('/api/v1/cases').get.mockReturnValue(respond({ folders: [], files: [] }))
    await listFolderEntries('case', 9, '')
    expect(client('/api/v1/cases').get).toHaveBeenCalledWith('9/folder-entries', { searchParams: {} })
  })

  it('kind=contract 走合同文件夹客户端（不是合同 CRUD 客户端）', async () => {
    clientAt(1).get.mockReturnValue(respond({ folders: [], files: [] }))
    await listFolderEntries('contract', 9, 'dir')
    expect(clientAt(1).get).toHaveBeenCalledWith('9/folder-entries', { searchParams: { subpath: 'dir' } })
    expect(clientAt(0).get).not.toHaveBeenCalled()
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

describe('另存为意图登记（只登记，不发字节）', () => {
  it('走 contracts/{id}/folder-save-as-intent，JSON 带 subpath + name', async () => {
    clientAt(1).post.mockReturnValue(respond({ registered: true, name: 'a[修订版]V1_20261027.docx', subpath: '1-合同/a.docx' }))
    await registerFolderSaveAsIntent('contract', 318, '1-合同/a.docx', 'a[修订版]V1_20261027.docx')
    expect(clientAt(1).post).toHaveBeenCalledWith('318/folder-save-as-intent', {
      json: { subpath: '1-合同/a.docx', name: 'a[修订版]V1_20261027.docx' },
    })
  })

  it('返回后端清洗后的实际文件名（可能与入参不同，提示语要用它）', async () => {
    clientAt(1).post.mockReturnValue(respond({ registered: true, name: 'a[修订版]V1_20261027_1.docx', subpath: '1-合同/a.docx' }))
    const res = await registerFolderSaveAsIntent('contract', 318, '1-合同/a.docx', 'x.docx')
    expect(res.name).toBe('a[修订版]V1_20261027_1.docx')
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
