/**
 * search api 拉平分组单测（node 环境即可）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient）。
 * 可测的是「合同+案件融合成 projects 类、按固定顺序拉平成统一 Hit 列表」
 * 与请求参数；防抖不在本层（消费方 GlobalSearch 自理）。
 */
import { describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/lib/api', () => ({
  createApiClient: () => ({ get: getMock }),
}))

import { CATEGORY_ORDER, runSearch } from './api'

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

describe('runSearch 分组拉平', () => {
  it('合同+案件融合为 projects（合同命中在前），其余类别按固定顺序垫后；未知类别丢弃', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        // 响应里顺序与固定顺序相反，且带未知类别 key
        contacts: [{ id: 7, title: '联系人-王五', subtitle: '' }],
        court_sms: [{ id: 6, title: '法院短信', subtitle: '' }],
        contracts: [{ id: 3, title: '王五委托合同', subtitle: '', case_type: 'civil' }],
        cases: [
          {
            id: 11,
            title: '王五一审案',
            subtitle: '(2026)粤01民初1号', // privacy-allow 虚构案号
            case_type: 'civil',
            contract_id: 3,
            contract_name: '王五委托合同',
          },
        ],
        clients: [{ id: 2, title: '客户-王五', subtitle: '' }],
        inbox: [{ id: 4, title: '收件箱', subtitle: '' }],
        unknown_entity: [{ id: 99, title: '不该出现', subtitle: '' }],
      }),
    )
    const hits = await runSearch('王五')
    expect(hits.map((h) => h.category)).toEqual([
      'projects',
      'projects',
      'clients',
      'inbox',
      'court_sms',
      'contacts',
    ])
    // 合同命中是项目行、案件命中挂项目下并透传合同字段（前端按此分组与路由分流）
    expect(hits[0]).toMatchObject({ kind: 'contract', id: 3, case_type: 'civil' })
    expect(hits[1]).toMatchObject({
      kind: 'case',
      id: 11,
      contract_id: 3,
      contract_name: '王五委托合同',
      case_type: 'civil',
    })
    // 未知类别被丢弃
    expect(hits.some((h) => h.id === 99)).toBe(false)
  })

  it('类别内保持后端数组顺序，字段透传为统一 Hit 形状（非当事人类 side 为空串）', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        cases: [
          { id: 11, title: '案件A', subtitle: '在办', side: '' },
          { id: 12, title: '案件B', subtitle: '已结案', side: '' },
        ],
      }),
    )
    const hits = await runSearch('案件')
    expect(hits).toEqual([
      { category: 'projects', kind: 'case', id: 11, title: '案件A', subtitle: '在办', side: '', case_type: '', contract_id: null, contract_name: '' },
      { category: 'projects', kind: 'case', id: 12, title: '案件B', subtitle: '已结案', side: '', case_type: '', contract_id: null, contract_name: '' },
    ])
  })

  it('当事人 side（我方/对方）原样透传；后端缺字段时兜成空串', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        clients: [
          { id: 2, title: '我方公司', subtitle: '13800000000', side: 'ours' }, // privacy-allow 虚构号码
          { id: 3, title: '对方公司', subtitle: '0757-22334455', side: 'opposing' }, // privacy-allow 虚构号码
          { id: 4, title: '旧后端无字段', subtitle: '' },
        ],
      }),
    )
    const hits = await runSearch('公司')
    expect(hits.map((h) => h.side)).toEqual(['ours', 'opposing', ''])
    // 电话原样透传，不在前端再做任何打码
    expect(hits[1]?.subtitle).toBe('0757-22334455') // privacy-allow 虚构号码
  })

  it('后端某类别缺字段（undefined/null）按空数组跳过', async () => {
    getMock.mockReturnValueOnce(respond({ cases: null, clients: undefined, contracts: [] }))
    const hits = await runSearch('无结果')
    expect(hits).toEqual([])
  })

  it('请求参数：q 随行、limit 固定 8（命中数收敛）', async () => {
    getMock.mockReturnValueOnce(respond({}))
    await runSearch('送达')
    expect(getMock).toHaveBeenCalledWith('', { searchParams: { q: '送达', limit: 8 } })
  })

  it('CATEGORY_ORDER 覆盖五类展示类别且 projects 在首', () => {
    expect(CATEGORY_ORDER).toEqual(['projects', 'clients', 'inbox', 'court_sms', 'contacts'])
  })
})
