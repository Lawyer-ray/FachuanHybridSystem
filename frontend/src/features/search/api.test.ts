/**
 * search api 拉平分组单测（node 环境即可）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient）。
 * runSearch 的防抖不在本层（消费方 GlobalSearch 自理），可测的是
 * 「按 CATEGORY_ORDER 固定顺序把各类命中拉平成统一 Hit 列表」与请求参数。
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
  it('按 CATEGORY_ORDER 固定顺序拉平（后端 key 乱序/多余不影响输出顺序）', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        // 响应里顺序与固定顺序相反，且带未知类别 key
        contacts: [{ id: 7, title: '联系人-王五', subtitle: '' }],
        court_sms: [{ id: 6, title: '法院短信', subtitle: '' }],
        contracts: [{ id: 3, title: '合同-王五', subtitle: '' }],
        cases: [{ id: 1, title: '案件-王五', subtitle: '在办' }],
        clients: [{ id: 2, title: '客户-王五', subtitle: '' }],
        inbox: [{ id: 4, title: '收件箱', subtitle: '' }],
        unknown_entity: [{ id: 99, title: '不该出现', subtitle: '' }],
      }),
    )
    const hits = await runSearch('王五')
    expect(hits.map((h) => h.category)).toEqual([
      'cases',
      'clients',
      'contracts',
      'inbox',
      'court_sms',
      'contacts',
    ])
    // 未知类别被丢弃
    expect(hits.some((h) => h.id === 99)).toBe(false)
  })

  it('类别内保持后端数组顺序，字段透传为统一 Hit 形状', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        cases: [
          { id: 11, title: '案件A', subtitle: '在办' },
          { id: 12, title: '案件B', subtitle: '已结案' },
        ],
      }),
    )
    const hits = await runSearch('案件')
    expect(hits).toEqual([
      { category: 'cases', id: 11, title: '案件A', subtitle: '在办' },
      { category: 'cases', id: 12, title: '案件B', subtitle: '已结案' },
    ])
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

  it('CATEGORY_ORDER 覆盖六类实体且为首导出的固定顺序', () => {
    expect(CATEGORY_ORDER).toEqual(['cases', 'clients', 'contracts', 'inbox', 'court_sms', 'contacts'])
  })
})
