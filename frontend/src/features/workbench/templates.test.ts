/**
 * templates：示例项目模板（node 环境）。
 *
 * 模板只负责「把新建项目表单的字段预先填好」，建出来的必须是**普通项目**——
 * 名字不带任何 [演示] 标记，材料仍要用户自己上传。断言聚焦这条产品约束，
 * 以及网络层的失败降级（客户/合同失败不阻断建案件，案件 id 拿不到才报错）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createFromTemplate, fetchSampleFile, findTemplate, PROJECT_TEMPLATES } from './templates'

/** ky 客户端桩：`post(path, opts).json()` 链；同一路径重复调用时依次取队列里的响应 */
function fakeApi(handlers: Record<string, Array<{ id?: number; name?: string } | Error>>) {
  const calls: Array<{ path: string; opts?: unknown }> = []
  const api = {
    post: vi.fn((path: string, opts?: unknown) => {
      calls.push({ path, opts })
      const queue = handlers[path] ?? []
      const next = queue.length > 1 ? queue.shift() : queue[0]
      const result = next instanceof Error ? Promise.reject(next) : Promise.resolve(next ?? {})
      return { json: () => result }
    }),
  }
  return { api, calls }
}

const EXISTING = PROJECT_TEMPLATES[0]!
const OPPOSING = EXISTING.their[0]!

describe('PROJECT_TEMPLATES：模板数据完整性', () => {
  it('每份模板都有唯一 key 与 UI 必需字段', () => {
    const keys = PROJECT_TEMPLATES.map((t) => t.key)
    expect(new Set(keys).size).toBe(keys.length)
    for (const t of PROJECT_TEMPLATES) {
      expect(t.title).toBeTruthy()
      expect(t.summary).toBeTruthy()
      expect(t.caseType).toBeTruthy()
      expect(t.stage).toBeTruthy()
      expect(t.cause).toBeTruthy()
      // 后端 Decimal 用字符串传，不能是 number
      expect(typeof t.targetAmount).toBe('string')
      expect(Number(t.targetAmount)).toBeGreaterThan(0)
    }
  })

  it('示例材料指向 public/demo-materials 静态资源', () => {
    for (const t of PROJECT_TEMPLATES) {
      expect(t.sample.file.startsWith('/demo-materials/')).toBe(true)
      expect(t.sample.file.endsWith('.pdf')).toBe(true)
      expect(t.sample.pages).toBeGreaterThan(0)
      expect(t.sample.docs).toBeGreaterThan(0)
    }
  })

  it('对方当事人至少有一个人，且都带脱敏标记', () => {
    for (const t of PROJECT_TEMPLATES) {
      expect(t.their.length).toBeGreaterThan(0)
      for (const p of t.their) {
        expect(p.name).toContain('某')
        expect(p.address).toContain('虚构')
      }
    }
  })
})

describe('findTemplate：按 key 查', () => {
  it('命中时返回同一份模板对象', () => {
    expect(findTemplate('mortgage_filing')).toBe(EXISTING)
  })

  it('未命中返回 undefined', () => {
    expect(findTemplate('nope')).toBeUndefined()
  })
})

describe('fetchSampleFile：示例材料 → File', () => {
  const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('200 时返回同名 File（URL 解码 + application/pdf）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, blob: async () => blob })))
    const file = await fetchSampleFile(EXISTING)
    expect(file).toBeInstanceOf(File)
    expect(file.name).toBe(decodeURIComponent(EXISTING.sample.file.split('/').pop()!))
    expect(file.type).toBe('application/pdf')
  })

  it('非 2xx 时带状态码抛错', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, blob: async () => blob })))
    await expect(fetchSampleFile(EXISTING)).rejects.toThrow('示例材料加载失败（404）')
  })

  it('路径以 / 结尾时文件名取到空串（`?? 示例材料.pdf` 兜不住空串——见报告 real bugs）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, blob: async () => blob })))
    const file = await fetchSampleFile({ ...EXISTING, sample: { ...EXISTING.sample, file: '/demo-materials/' } })
    expect(file.name).toBe('')
  })
})

describe('createFromTemplate：建普通项目', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-20T08:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup() {
    // 客户接口每次调用返回新 id（模板有 1 个我方 + N 个对方当事人）；
    // 队列用完后重复最后一项——breakdown 用例靠这一点让每个当事人拿到不同 id
    const { api: clientApi, calls: clientCalls } = fakeApi({
      clients: [{ id: 101 }, { id: 202 }],
    })
    const { api: contractApi, calls: contractCalls } = fakeApi({
      'contracts/full': [{ id: 55 }],
    })
    const { api: caseApi, calls: caseCalls } = fakeApi({
      'cases/full': [{ id: 999, name: '建出来的案件名' }],
    })
    return { clientApi, clientCalls, contractApi, contractCalls, caseApi, caseCalls }
  }

  it('返回 contractId / caseId / caseName，且案件名由后端返回优先', async () => {
    const { clientApi, contractApi, caseApi } = setup()
    const out = await createFromTemplate(EXISTING, {
      projectName: '某某银行诉谭某某',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    expect(out).toEqual({ contractId: 55, caseId: 999, caseName: '建出来的案件名' })
  })

  it('客户逐个创建：我方 1 个法人 + 对方每个自然人', async () => {
    const { clientApi, clientCalls, contractApi, caseApi } = setup()
    await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    const expectedClientCalls = 1 + EXISTING.their.length
    expect(clientCalls.map((c) => c.path)).toEqual(Array.from({ length: expectedClientCalls }, () => 'clients'))
    const bodies = clientCalls.map((c) => (c.opts as { json: Record<string, unknown> }).json)
    expect(bodies[0]).toMatchObject({
      name: EXISTING.our.name,
      client_type: 'legal',
      is_our_client: true,
      legal_representative: EXISTING.our.legalRep,
    })
    expect(bodies[1]).toMatchObject({
      name: OPPOSING.name,
      client_type: 'natural',
      is_our_client: false,
    })
  })

  it('合同字段：名字带「·委托合同」、日期取今天、阶段与律师透传', async () => {
    const { clientApi, contractApi, contractCalls, caseApi } = setup()
    await createFromTemplate(EXISTING, {
      projectName: '某某银行诉谭某某',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    const json = (contractCalls[0]?.opts as { json: Record<string, unknown> }).json
    expect(json).toMatchObject({
      name: '某某银行诉谭某某·委托合同',
      case_type: EXISTING.caseType,
      status: 'active',
      start_date: '2026-10-20',
      representation_stages: [EXISTING.stage],
      lawyer_ids: [7],
      fee_mode: 'FIXED',
      parties: [{ client_id: 101, role: 'PRINCIPAL' }],
      cases: [],
    })
  })

  it('案件字段：当事人分原告/被告、指派、管辖法院', async () => {
    const { clientApi, contractApi, caseApi, caseCalls } = setup()
    await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    const body = (caseCalls[0]?.opts as { json: Record<string, unknown> }).json as {
      case: Record<string, unknown>
      parties: unknown[]
      assignments: unknown[]
      supervising_authorities: unknown[]
    }
    expect(body.case).toMatchObject({
      case_type: EXISTING.caseType,
      status: 'active',
      current_stage: EXISTING.stage,
      cause_of_action: EXISTING.cause,
      target_amount: EXISTING.targetAmount,
    })
    expect(body.parties).toEqual([
      { client_id: 101, legal_status: 'plaintiff' },
      ...EXISTING.their.map(() => ({ client_id: 202, legal_status: 'defendant' })),
    ])
    expect(body.assignments).toEqual([{ lawyer_id: 7 }])
    expect(body.supervising_authorities).toEqual([{ name: EXISTING.court, authority_type: 'trial' }])
  })

  it('客户建失败 → 当事人数组为空，但不阻断建案件', async () => {
    const clientApi = { post: vi.fn(() => ({ json: () => Promise.reject(new Error('重名')) })) }
    const { api: contractApi } = fakeApi({ 'contracts/full': [{ id: 55 }] })
    const { api: caseApi, calls: caseCalls } = fakeApi({ 'cases/full': [{ id: 999, name: 'N' }] })
    const out = await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    expect(out.caseId).toBe(999)
    const body = (caseCalls[0]?.opts as { json: { parties: unknown[] } }).json
    expect(body.parties).toEqual([])
  })

  it('合同建失败 → contractId 为 null，案件照建（OA 立案用不了而已）', async () => {
    const { clientApi } = setup()
    const contractApi = { post: vi.fn(() => ({ json: () => Promise.reject(new Error('500')) })) }
    const { api: caseApi } = fakeApi({ 'cases/full': [{ id: 999, name: 'N' }] })
    const out = await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    expect(out.contractId).toBeNull()
    expect(out.caseId).toBe(999)
  })

  it('合同返回没有 id 时 contractId 为 null', async () => {
    const { clientApi } = setup()
    const { api: contractApi } = fakeApi({ 'contracts/full': [{}] })
    const { api: caseApi } = fakeApi({ 'cases/full': [{ id: 999, name: 'N' }] })
    const out = await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    expect(out.contractId).toBeNull()
  })

  it('后端没返回案件 id 时报「建项目失败」', async () => {
    const { clientApi } = setup()
    const { api: contractApi } = fakeApi({ 'contracts/full': [{ id: 55 }] })
    const { api: caseApi } = fakeApi({ 'cases/full': [{}] })
    await expect(
      createFromTemplate(EXISTING, {
        projectName: 'P',
        lawyerId: 7,
        caseApi: caseApi as never,
        contractApi: contractApi as never,
        clientApi: clientApi as never,
      }),
    ).rejects.toThrow('建项目失败：后端未返回案件 id')
  })

  it('后端没返回案件名时回退到本地拼的名字', async () => {
    const { clientApi } = setup()
    const { api: contractApi } = fakeApi({ 'contracts/full': [{ id: 55 }] })
    const { api: caseApi } = fakeApi({ 'cases/full': [{ id: 999 }] })
    const out = await createFromTemplate(EXISTING, {
      projectName: 'P',
      lawyerId: 7,
      caseApi: caseApi as never,
      contractApi: contractApi as never,
      clientApi: clientApi as never,
    })
    expect(out.caseName).toBe(`P·${EXISTING.their.map((x) => x.name).join('、')}${EXISTING.cause}`)
  })
})
