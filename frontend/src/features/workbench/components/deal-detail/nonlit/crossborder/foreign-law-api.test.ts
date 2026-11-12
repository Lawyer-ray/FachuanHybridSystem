/**
 * foreign-law-api：泰国法核验的真接口契约（node 环境）。
 *
 * 两个实测踩过的坑在这里钉死：
 *   · `country_code` 必须 `LAWCOUNTRYTG`（BARLC 的国家代码，不是 ISO 的 TH，传 TH 会 422）
 *   · `law_name` 用「民商法典」而不是「泰国民商法典」（带国名前缀查不到）
 * 接口实测 6–8 秒，所以超时给到 30 秒。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{ prefix: string; post: ReturnType<typeof vi.fn> }>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const client = { prefix: opts?.prefix ?? '/api/v1', post: vi.fn() }
    clients.push(client)
    return client
  },
}))

import {
  BARLC_THAILAND,
  DEMO_THAI_CITATIONS,
  verifyThaiLaw,
  type ThaiLawCitation,
} from './foreign-law-api'

function client() {
  const c = clients[0]
  if (!c) throw new Error('客户端未创建')
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

const CITATION: ThaiLawCitation = {
  article: '第三条 租金',
  lawName: '民商法典',
  section: '538',
  claim: '单方将 CPI 全额转嫁缺乏对价平衡',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('客户端与常量', () => {
  it('挂 /api/v1/legal-research/foreign-law 前缀', () => {
    expect(client().prefix).toBe('/api/v1/legal-research/foreign-law')
  })

  it('国家代码是 BARLC 的 LAWCOUNTRYTG（不是 ISO 的 TH）', () => {
    expect(BARLC_THAILAND).toBe('LAWCOUNTRYTG')
  })
})

describe('DEMO_THAI_CITATIONS', () => {
  it('只留 3 条真实可查的引用（演示时每条都等得起）', () => {
    expect(DEMO_THAI_CITATIONS).toHaveLength(3)
    expect(DEMO_THAI_CITATIONS.map((c) => c.section)).toEqual(['538', '546', '549'])
  })

  it('法名一律「民商法典」（带国名前缀查不到）', () => {
    for (const c of DEMO_THAI_CITATIONS) expect(c.lawName).toBe('民商法典')
  })

  it('每条都带合同里的位置、条文号与主张', () => {
    for (const c of DEMO_THAI_CITATIONS) {
      expect(c.article).toBeTruthy()
      expect(c.section).toBeTruthy()
      expect(c.claim.length).toBeGreaterThan(5)
    }
  })
})

describe('verifyThaiLaw', () => {
  it('POST verify，字段名与后端一致（law_name / section_number / claim / country_code）', async () => {
    client().post.mockReturnValue(respond({ ok: true, section_text: 'Section text' }))
    const out = await verifyThaiLaw(CITATION)
    expect(out.ok).toBe(true)
    const [path, opts] = client().post.mock.calls[0]!
    expect(path).toBe('verify')
    expect(opts.json).toEqual({
      law_name: '民商法典',
      section_number: '538',
      claim: '单方将 CPI 全额转嫁缺乏对价平衡',
      country_code: 'LAWCOUNTRYTG',
    })
  })

  it('超时给到 30 秒（接口实测 6–8 秒，要留余量）', async () => {
    client().post.mockReturnValue(respond({ ok: true }))
    await verifyThaiLaw(CITATION)
    expect(client().post.mock.calls[0]![1].timeout).toBe(30_000)
  })

  it('失败结果原样返回（ok=false + reason，由调用方显示「查不到」）', async () => {
    const failure = { ok: false, reason: 'BARLC 未收录该条文' }
    client().post.mockReturnValue(respond(failure))
    await expect(verifyThaiLaw(CITATION)).resolves.toEqual(failure)
  })
})
