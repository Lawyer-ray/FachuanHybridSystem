/**
 * workbench/api/stages 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient（contracts 客户端）；断言聚焦
 * 后端 `children/doc/ver/data` 与前端 `folders/name/version/startDate` 的双向适配，
 * 以及端点未上线时的降级（读失败抛出由 hook 兜成空树，写回空响应回退本地树）。
 *
 * 子阶段静默消失是实测踩过的坑：后端 `children` 被 normalizeTree 当未知字段丢掉，
 * API 返回 2 个子阶段页面上只剩 5 个顶层阶段。
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

import type { PhaseNode } from '../components/deal-detail/special-phase-tree'

import { getContractStages, putContractStages } from './stages'

/** 按前缀取客户端（stages 只用 contractsApi 一个） */
function contractsClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/contracts')
  if (!c) throw new Error('contracts 客户端未创建')
  return c
}

/** ky 链桩：`client.get(...).json()` / `client.put(...).json()` */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getContractStages：后端 → 前端', () => {
  it('GET 走 contracts/{id}/stages', async () => {
    contractsClient().get.mockReturnValue(respond({ stages: [] }))
    await getContractStages(42)
    expect(contractsClient().get).toHaveBeenCalledWith('contracts/42/stages')
  })

  it('后端 children 适配成 folders（子阶段不丢）', async () => {
    contractsClient().get.mockReturnValue(
      respond({
        stages: [
          {
            key: 'ph_1',
            name: '尽职调查',
            acceptance: '四项底稿齐',
            date: '2026-10-26',
            open: true,
            children: [
              { key: 'ph_1_1', name: '工商核查', date: '2026-10-27', children: [] },
              { key: 'ph_1_2', name: '社保核查', children: [] },
            ],
            deliverables: [],
          },
        ],
      }),
    )
    const tree = await getContractStages(1)
    expect(tree[0]).toMatchObject({
      key: 'ph_1',
      name: '尽职调查',
      acceptance: '四项底稿齐',
      startDate: '2026-10-26',
      open: true,
      deliverables: [],
    })
    expect(tree[0]?.folders.map((f) => f.name)).toEqual(['工商核查', '社保核查'])
    expect(tree[0]?.folders[0]?.startDate).toBe('2026-10-27')
  })

  it('无 children 时退回 folders 字段（前端形状往返）', async () => {
    contractsClient().get.mockReturnValue(
      respond({ stages: [{ key: 'k', name: 'n', folders: [{ key: 'k2', name: '子' }] }] }),
    )
    const tree = await getContractStages(1)
    expect(tree[0]?.folders.map((f) => f.name)).toEqual(['子'])
  })

  it('交付物 doc/ver 适配成 name/version，subpath 决定 planned', async () => {
    contractsClient().get.mockReturnValue(
      respond({
        stages: [
          {
            key: 'k',
            name: 'n',
            children: [],
            deliverables: [
              { date: '2026-10-03', doc: '《股东协议》', ver: 'v2', state: 'ok', subpath: 'p/a.docx' },
              { date: '', doc: '《清算方案》', ver: '', state: 'todo' },
            ],
          },
        ],
      }),
    )
    const [node] = await getContractStages(1)
    expect(node?.deliverables).toEqual([
      { id: 'p/a.docx', date: '2026-10-03', name: '《股东协议》', version: 'v2', state: 'ok', subpath: 'p/a.docx', planned: false },
      { id: '《清算方案》', date: '', name: '《清算方案》', version: '', state: 'todo', subpath: undefined, planned: true },
    ])
  })

  it('交付物 id：优先用后端给的 id 字符串，否则按 subpath → 文书名依次取', async () => {
    contractsClient().get.mockReturnValue(
      respond({
        stages: [
          {
            key: 'k',
            name: 'n',
            deliverables: [
              { id: 'fixed', name: '《A》', subpath: 'p/a.pdf' },
              { name: '《B》', subpath: 'p/b.pdf' },
              { name: '《C》' },
            ],
          },
        ],
      }),
    )
    const [node] = await getContractStages(1)
    expect(node?.deliverables.map((d) => d.id)).toEqual(['fixed', 'p/b.pdf', '《C》'])
  })

  it('空响应 / null stages 都降级成空树', async () => {
    contractsClient().get.mockReturnValue(respond({}))
    expect(await getContractStages(1)).toEqual([])
    contractsClient().get.mockReturnValue(respond(null))
    expect(await getContractStages(1)).toEqual([])
  })

  it('松散节点补默认值（缺 name 时「未命名阶段」）', async () => {
    contractsClient().get.mockReturnValue(respond({ stages: [{ key: 'k' }] }))
    const [node] = await getContractStages(1)
    expect(node).toMatchObject({ name: '未命名阶段', acceptance: '', startDate: '', open: false })
  })
})

describe('putContractStages：前端 → 后端（与 fromBackendNode 互逆）', () => {
  function sampleTree(): PhaseNode[] {
    return [
      {
        key: 'ph_1',
        name: '尽职调查',
        acceptance: '四项底稿齐',
        open: true,
        startDate: '2026-10-26',
        folders: [
          {
            key: 'ph_1_1',
            name: '工商核查',
            acceptance: '',
            open: false,
            startDate: '',
            folders: [],
            deliverables: [{ id: 'd1', date: '2026-10-03', name: '《股东协议》', version: 'v2', state: 'ok', subpath: 'p/a.docx', planned: false }],
          },
        ],
        deliverables: [],
      },
    ]
  }

  it('PUT 路径与 body 形状（children/date/doc/ver，open 随行）', async () => {
    contractsClient().put.mockReturnValue(respond({ stages: sampleTree() }))
    await putContractStages(42, sampleTree())
    const [path, opts] = contractsClient().put.mock.calls[0]!
    expect(path).toBe('contracts/42/stages')
    expect(opts.json).toEqual({
      stages: [
        {
          key: 'ph_1',
          name: '尽职调查',
          acceptance: '四项底稿齐',
          date: '2026-10-26',
          open: true,
          children: [
            {
              key: 'ph_1_1',
              name: '工商核查',
              acceptance: '',
              date: '',
              open: false,
              children: [],
              deliverables: [
                { date: '2026-10-03', doc: '《股东协议》', ver: 'v2', state: 'ok', subpath: 'p/a.docx', planned: false },
              ],
            },
          ],
          deliverables: [],
        },
      ],
    })
  })

  it('后端返回 stages 时用返回值（再经适配成前端形状）', async () => {
    contractsClient().put.mockReturnValue(
      respond({ stages: [{ key: 'ph_1', name: '改名后', children: [] }] }),
    )
    const out = await putContractStages(1, sampleTree())
    expect(out.map((n) => n.name)).toEqual(['改名后'])
  })

  it('后端返回空 stages 时回退到提交的本地树（端点未上线不丢改动）', async () => {
    contractsClient().put.mockReturnValue(respond({ stages: [] }))
    const submitted = sampleTree()
    const out = await putContractStages(1, submitted)
    expect(out).toBe(submitted)
  })

  it('折返一次后结构与交付物一致，唯 id 按 subpath 重推（后端不存交付物 id）', async () => {
    const submitted = sampleTree()
    contractsClient().put.mockReturnValue(
      respond({
        stages: [
          {
            key: 'ph_1',
            name: '尽职调查',
            acceptance: '四项底稿齐',
            date: '2026-10-26',
            open: true,
            children: [
              {
                key: 'ph_1_1',
                name: '工商核查',
                acceptance: '',
                date: '',
                open: false,
                children: [],
                deliverables: [
                  { date: '2026-10-03', doc: '《股东协议》', ver: 'v2', state: 'ok', subpath: 'p/a.docx', planned: false },
                ],
              },
            ],
            deliverables: [],
          },
        ],
      }),
    )
    const out = await putContractStages(1, submitted)
    // toBackendNode 不写交付物 id（后端不存），回来时按 subpath 重推
    const expected = structuredClone(submitted)
    expected[0]!.folders[0]!.deliverables[0]!.id = 'p/a.docx'
    expect(out).toMatchObject(expected)
  })
})
