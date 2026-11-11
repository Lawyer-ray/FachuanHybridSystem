/**
 * 归案链路单测（node 环境）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient）：按 prefix 建出的
 * 客户端（/api/v1 核心、/api/v1/cases、/api/v1/client、/api/v1/contracts、
 * /api/v1/inbox、/api/v1/organization）各自可寻址，断言聚焦「每一步请求了
 * 什么路径 / body」，以及链路的容错语义（合同失败不阻断归案、单份绑定失败
 * 不中断其余分段、取不到律师直接抛错）。端点形状取自后端 OpenAPI，不是猜的。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { clients } = vi.hoisted(() => ({
  clients: [] as Array<{
    prefix: string
    get: ReturnType<typeof vi.fn>
    post: ReturnType<typeof vi.fn>
  }>,
}))

/**
 * 每个 prefix 只建一次桩实例：cases.ts 里 `createApiClient(...)` 写在函数体内
 * （currentLawyerId / ensureClient / uploadSegment），若每次都新建实例，
 * 用例在固定实例上挂的桩就打不中新实例，断言也无处取调用记录。
 * 按 prefix 复用既符合真实语义（ky 客户端本就该复用），也让断言稳定。
 */
vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = clients.find((x) => x.prefix === prefix)
    if (existing) return existing
    const client = { prefix, get: vi.fn(), post: vi.fn() }
    clients.push(client)
    return client
  },
}))

import { assignPack, currentLawyerId, searchCases } from './cases'

/** 按 prefix 取第一个客户端桩（模块加载即建好的那几个用它断言） */
function client(prefix: string) {
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

/** 失败桩：与 ky 一致，await 与 .json() 都抛 */
function fail(error: Error) {
  const p = Promise.reject(error)
  p.catch(() => {}) // 用例里必然 await / catch，这里只防未处理 rejection 噪音
  return Object.assign(p, { json: () => p })
}

/**
 * 确保某前缀的客户端桩已存在：/api/v1/organization 只有在 currentLawyerId 里才会
 * `createApiClient` 现建，用例若在调用前就挂桩，必须先把它“提出来”（按 prefix
 * 复用实例，见文件头 mock 说明）。
 */
function ensurePrefix(prefix: string) {
  if (!clients.some((c) => c.prefix === prefix)) {
    clients.push({ prefix, get: vi.fn(), post: vi.fn() })
  }
}

/** 某一前缀所有实例收到的请求（跨「函数体内现建」的多个实例汇总） */
function callsOf(prefix: string, method: 'get' | 'post'): unknown[][] {
  return clients
    .filter((c) => c.prefix === prefix)
    .flatMap((c) => c[method].mock.calls as unknown[][])
}

/**
 * 给某前缀**所有现存实例**挂桩。
 *
 * ⚠️ `currentLawyerId` / `ensureClient` 里的 `createApiClient(...)` 写在函数体内，
 * 每次调用都新建实例 —— 只对第一个实例 `mockReturnValue` 只能影响其中一次调用。
 * 所以统一用 mockImplementation 批量挂，并在 beforeEach 里批量挂一次；
 * 断言一律走 callsOf（台账），不绑定具体实例。
 */
function stubAll(prefix: string, handlers: { get?: (path: string) => unknown; post?: (path: string) => unknown }) {
  ensurePrefix(prefix)
  for (const c of clients.filter((x) => x.prefix === prefix)) {
    if (handlers.get) c.get.mockImplementation((path: string) => handlers.get!(path))
    if (handlers.post) c.post.mockImplementation((path: string) => handlers.post!(path))
  }
}

const SEGMENT = { name: '起诉状', partIndex: 0, pageStart: 1, pageEnd: 3 }

/** 归案默认桩：律师 42 / 客户 5 / 合同 88 / 案件 3001 / 附件 101 / 绑定成功 */
function stubHappyPath() {
  stubAll('/api/v1/organization', { get: () => respond({ id: 42 }) })
  stubAll('/api/v1/client', { post: () => respond({ id: 5 }) })
  stubAll('/api/v1/contracts', { post: () => respond({ id: 88 }) })
  stubAll('/api/v1/inbox', { get: () => respond({ blob: () => Promise.resolve(new Blob(['pdf'])) }) })
  stubAll('/api/v1/cases', {
    get: () => respond({ name: '既有案件' }),
    post: (path: string) => {
      if (path === 'cases/full') return respond({ id: 3001, name: '谭某某借款纠纷' })
      if (path.endsWith('/materials/upload')) return respond({ attachment_ids: [101] })
      return respond({})
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  stubHappyPath()
})

describe('searchCases', () => {
  it('空白关键字短路返回 []，不发请求', async () => {
    await expect(searchCases('   ')).resolves.toEqual([])
    expect(callsOf('/api/v1', 'get')).toEqual([])
  })

  it('非空关键字带 q 与 limit=10，signal 透传支持取消', async () => {
    const core = client('/api/v1')
    core.get.mockReturnValue(respond([{ id: 1 }]))
    const ac = new AbortController()
    await expect(searchCases('谭某某', ac.signal)).resolves.toEqual([{ id: 1 }])
    expect(core.get).toHaveBeenCalledWith('cases/search', {
      searchParams: { q: '谭某某', limit: '10' },
      signal: ac.signal,
    })
  })
})

describe('currentLawyerId', () => {
  it('优先取 /organization/me 的 id，命中即不再查律师列表', async () => {
    await expect(currentLawyerId()).resolves.toBe(42)
    expect(callsOf('/api/v1/organization', 'get')).toEqual([['me']])
  })

  it('me 取不到 id 时回落到律师列表（数组形状）', async () => {
    stubAll('/api/v1/organization', {
      get: (path) => (path === 'me' ? respond({}) : respond([{ id: 9 }])),
    })
    await expect(currentLawyerId()).resolves.toBe(9)
    expect(callsOf('/api/v1/organization', 'get').map((c) => c[0])).toEqual(['me', 'lawyers'])
  })

  it('律师列表是分页信封时取 items[0]', async () => {
    stubAll('/api/v1/organization', {
      get: (path) => (path === 'me' ? respond(null) : respond({ items: [{ id: 11 }] })),
    })
    await expect(currentLawyerId()).resolves.toBe(11)
  })

  it('两条路都拿不到 id 时抛错提示重新登录', async () => {
    stubAll('/api/v1/organization', {
      get: (path) => (path === 'me' ? fail(new Error('401')) : respond([])),
    })
    await expect(currentLawyerId()).rejects.toThrow('无法确定当前律师，请重新登录')
  })
})

describe('assignPack：target=new', () => {
  it('建客户 → 建合同 → 建案 → 逐段绑定，返回归案摘要', async () => {
    const res = await assignPack({
      messageId: 9,
      target: 'new',
      caseName: '谭某某借款纠纷',
      court: '某某人民法院',
      cause: '金融借款合同纠纷',
      targetAmount: '100000',
      parties: { our: '某某银行', their: '谭某某、梁某某' },
      segments: [SEGMENT],
    })

    expect(res).toEqual({ caseId: 3001, caseName: '谭某某借款纠纷', contractId: 88, boundCount: 1 })

    // 我方 + 两个对方各建一次客户；含「银行」字样的按法人主体建
    const clientBodies = callsOf('/api/v1/client', 'post').map(
      (c) => (c[1] as { json: { name: string; is_our_client: boolean; client_type: string } }).json,
    )
    expect(clientBodies.map((j) => j.name)).toEqual(['某某银行', '谭某某', '梁某某'])
    expect(clientBodies.map((j) => j.is_our_client)).toEqual([true, false, false])
    expect(clientBodies.map((j) => j.client_type)).toEqual(['legal', 'natural', 'natural'])

    // 合同必须带代理阶段（不给的话详情页与左栏程序节点条画不出来）
    const [contractPath, contractReq] = callsOf('/api/v1/contracts', 'post')[0]!
    expect(contractPath).toBe('contracts/full')
    expect((contractReq as { json: { representation_stages: string[] } }).json.representation_stages).toEqual([
      'first_trial',
      'second_trial',
      'enforcement',
    ])

    // 案件一次建齐：当事人 / 主办律师 / 管辖法院
    const caseCalls = callsOf('/api/v1/cases', 'post')
    const caseBody = (
      caseCalls.find((c) => c[0] === 'cases/full')![1] as {
        json: {
          parties: Array<{ legal_status: string }>
          assignments: Array<{ lawyer_id: number }>
          supervising_authorities: Array<{ name: string; authority_type: string }>
          case: { cause_of_action: string; target_amount: string | null }
        }
      }
    ).json
    expect(caseBody.parties.map((p) => p.legal_status)).toEqual(['plaintiff', 'defendant', 'defendant'])
    expect(caseBody.assignments).toEqual([{ lawyer_id: 42 }])
    expect(caseBody.supervising_authorities).toEqual([{ name: '某某人民法院', authority_type: 'trial' }])
    expect(caseBody.case).toMatchObject({ cause_of_action: '金融借款合同纠纷', target_amount: '100000' })

    // 绑定打到新建案件 id 上
    expect(caseCalls.map((c) => c[0]).filter((p) => String(p).includes('materials'))).toEqual([
      '3001/materials/upload',
      '3001/materials/bind',
    ])
  })

  it('合同建不出来不阻断归案，contractId 回落为 null', async () => {
    stubAll('/api/v1/contracts', { post: () => fail(new Error('500')) })
    const res = await assignPack({
      messageId: 9,
      target: 'new',
      parties: { our: '', their: '' },
      segments: [],
    })
    expect(res.contractId).toBeNull()
    expect(res.caseId).toBe(3001)
    expect(res.boundCount).toBe(0)
  })

  it('当事人为空时既不建客户，也不在案件里塞当事人与管辖法院', async () => {
    await assignPack({ messageId: 9, target: 'new', parties: { our: '', their: '' }, segments: [] })
    expect(callsOf('/api/v1/client', 'post')).toEqual([])
    const caseBody = (
      callsOf('/api/v1/cases', 'post').find((c) => c[0] === 'cases/full')![1] as {
        json: { parties: unknown[]; supervising_authorities: unknown[] }
      }
    ).json
    expect(caseBody.parties).toEqual([])
    expect(caseBody.supervising_authorities).toEqual([])
  })

  it('附件取不到时跳过该段，其余段照常绑定', async () => {
    // 第一个分段取不到字节，第二个正常
    let nth = 0
    stubAll('/api/v1/inbox', {
      get: () => {
        nth += 1
        return nth === 1 ? fail(new Error('410')) : respond({ blob: () => Promise.resolve(new Blob(['pdf'])) })
      },
    })

    const res = await assignPack({
      messageId: 9,
      target: 'new',
      parties: { our: '', their: '' },
      segments: [SEGMENT, { ...SEGMENT, name: '证据', partIndex: 1 }],
    })
    expect(res.boundCount).toBe(1)
    expect(callsOf('/api/v1/cases', 'post').filter((c) => String(c[0]).endsWith('/materials/bind'))).toHaveLength(1)
  })

  it('上传未返回附件 id 时该段不建材料', async () => {
    stubAll('/api/v1/cases', {
      post: (path) => {
        if (path === 'cases/full') return respond({ id: 3001, name: '案件' })
        if (path.endsWith('/materials/upload')) return respond({ attachment_ids: [] })
        return respond({})
      },
    })

    const res = await assignPack({
      messageId: 9,
      target: 'new',
      parties: { our: '', their: '' },
      segments: [SEGMENT],
    })
    expect(res.boundCount).toBe(0)
    expect(callsOf('/api/v1/cases', 'post').some((c) => String(c[0]).endsWith('/materials/bind'))).toBe(false)
  })

  it('单段绑定失败不中断后续分段', async () => {
    let bindCalls = 0
    stubAll('/api/v1/cases', {
      post: (path) => {
        if (path === 'cases/full') return respond({ id: 3001, name: '案件' })
        if (path.endsWith('/materials/upload')) return respond({ attachment_ids: [101] })
        bindCalls += 1
        return bindCalls === 1 ? fail(new Error('409')) : respond({})
      },
    })

    const res = await assignPack({
      messageId: 9,
      target: 'new',
      parties: { our: '', their: '' },
      segments: [SEGMENT, { ...SEGMENT, name: '证据' }],
    })
    expect(bindCalls).toBe(2)
    expect(res.boundCount).toBe(1)
  })

  it('后端未返回案件 id 时抛出建案失败', async () => {
    stubAll('/api/v1/cases', { post: () => respond({}) })
    await expect(
      assignPack({ messageId: 9, target: 'new', parties: { our: '', their: '' }, segments: [] }),
    ).rejects.toThrow('建案失败：后端未返回案件 id')
  })

  it('未指定 caseName 时用「新材料」兜底命名合同与案件', async () => {
    await assignPack({ messageId: 9, target: 'new', parties: { our: '', their: '' }, segments: [] })
    expect((callsOf('/api/v1/contracts', 'post')[0]![1] as { json: { name: string } }).json.name).toBe(
      '新材料·委托合同',
    )
    expect(
      (callsOf('/api/v1/cases', 'post').find((c) => c[0] === 'cases/full')![1] as {
        json: { case: { name: string } }
      }).json.case.name,
    ).toBe('新材料归案案件')
  })
})

describe('assignPack：target=existing', () => {
  it('只取案件名，不建客户与合同，然后逐段绑定到该案件', async () => {
    const res = await assignPack({
      messageId: 9,
      target: 'existing',
      caseId: 55,
      parties: { our: '某某银行', their: '谭某某' },
      segments: [SEGMENT],
    })

    expect(res).toEqual({ caseId: 55, caseName: '既有案件', contractId: null, boundCount: 1 })
    expect(callsOf('/api/v1/cases', 'get')).toEqual([['cases/55']])
    expect(callsOf('/api/v1/client', 'post')).toEqual([])
    expect(callsOf('/api/v1/contracts', 'post')).toEqual([])
    expect(callsOf('/api/v1/cases', 'post').map((c) => c[0])).toEqual([
      '55/materials/upload',
      '55/materials/bind',
    ])
  })

  it('案件详情取不到名字时 caseName 回落空串（不因取名失败而中止归案）', async () => {
    stubAll('/api/v1/cases', { get: () => respond({}), post: () => respond({}) })
    const res = await assignPack({
      messageId: 9,
      target: 'existing',
      caseId: 55,
      parties: { our: '', their: '' },
      segments: [],
    })
    expect(res.caseName).toBe('')
  })
})
