import { describe, expect, it } from 'vitest'

import { groupProjects, orderProjectHits, projectRoute } from './domain'
import type { Hit } from './types'

/** 构造 projects 命中（合同/案件）；其余类别只用于 orderProjectHits 的垫后序断言 */
function hit(category: string, id: number, over: Partial<Hit> = {}): Hit {
  return {
    category,
    id,
    title: `#${id}`,
    subtitle: '',
    side: '',
    case_type: '',
    contract_id: null,
    contract_name: '',
    ...over,
  }
}

describe('groupProjects 项目分组', () => {
  it('合同命中作组头，同合同案件命中挂其下；合同没命中时用案件携带的合同信息补组头', () => {
    const { groups, orphans } = groupProjects([
      hit('projects', 3, { kind: 'contract', title: '王五委托合同', case_type: 'civil' }),
      hit('projects', 11, { kind: 'case', title: '王五一审案', contract_id: 3, contract_name: '王五委托合同', case_type: 'civil' }),
      hit('projects', 12, { kind: 'case', title: '王五二审案', contract_id: 3, contract_name: '王五委托合同', case_type: 'civil' }),
      hit('projects', 21, { kind: 'case', title: '赵六常法日常事务', contract_id: 9, contract_name: '赵六常年法律顾问合同', case_type: 'advisor' }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      contractId: 3,
      title: '王五委托合同',
      contractHit: expect.objectContaining({ kind: 'contract' }),
      caseHits: [expect.objectContaining({ id: 11 }), expect.objectContaining({ id: 12 })],
    })
    // 合同 9 没命中：组头来自案件携带的信息，不可点
    expect(groups[1]).toMatchObject({ contractId: 9, title: '赵六常年法律顾问合同', contractHit: null, case_type: 'advisor' })
    expect(orphans).toEqual([])
  })

  it('无合同的案件（contract_id 空）进 orphans，不建组', () => {
    const { groups, orphans } = groupProjects([
      hit('projects', 11, { kind: 'case', title: '历史孤案' }),
    ])
    expect(groups).toEqual([])
    expect(orphans.map((h) => h.title)).toEqual(['历史孤案'])
  })
})

describe('orderProjectHits 键盘序', () => {
  it('projects 段按「组头 → 案件」重排，其余类别原序垫后', () => {
    const ordered = orderProjectHits([
      hit('projects', 3, { kind: 'contract', title: '合同A', case_type: 'civil' }),
      hit('projects', 5, { kind: 'contract', title: '合同B', case_type: 'civil' }),
      hit('projects', 11, { kind: 'case', title: 'A的一审', contract_id: 3, contract_name: '合同A' }),
      hit('clients', 2, { title: '客户甲' }),
      hit('projects', 12, { kind: 'case', title: 'B的二审', contract_id: 5, contract_name: '合同B' }),
      hit('inbox', 7, { title: '收件' }),
    ])
    expect(ordered.map((h) => h.title)).toEqual(['合同A', 'A的一审', '合同B', 'B的二审', '客户甲', '收件'])
  })

  it('orphan 案件排在 projects 组之后、其余类别之前', () => {
    const ordered = orderProjectHits([
      hit('projects', 11, { kind: 'case', title: '孤案' }),
      hit('projects', 3, { kind: 'contract', title: '合同A' }),
      hit('clients', 2, { title: '客户甲' }),
    ])
    expect(ordered.map((h) => h.title)).toEqual(['合同A', '孤案', '客户甲'])
  })
})

describe('projectRoute 路由分流', () => {
  it('诉讼/非诉合同都走单条 /projects/:id（详情页内部按 lit 选左栏，不再有 /nonlit）', () => {
    expect(projectRoute(hit('projects', 3, { kind: 'contract', case_type: 'civil' }))).toBe('/projects/3')
    // 回归：advisor（常法顾问）曾拼出 /projects/4/nonlit，撞通配重定向跳回首页
    expect(projectRoute(hit('projects', 4, { kind: 'contract', case_type: 'advisor' }))).toBe('/projects/4')
  })

  it('案件 → 所属合同的项目页，诉讼带 #case-<id> 锚点滚到该案，非诉不带', () => {
    expect(
      projectRoute(hit('projects', 11, { kind: 'case', contract_id: 5, case_type: 'civil' })),
    ).toBe('/projects/5#case-11')
    expect(
      projectRoute(hit('projects', 21, { kind: 'case', contract_id: 9, case_type: 'special' })),
    ).toBe('/projects/9#case-21')
  })

  it('生成的路由不带 /nonlit 后缀（该路由已不存在，带后缀必然落到通配 → 首页）', () => {
    const all = [
      projectRoute(hit('projects', 1, { kind: 'contract', case_type: 'advisor' })),
      projectRoute(hit('projects', 2, { kind: 'contract', case_type: 'special' })),
      projectRoute(hit('projects', 3, { kind: 'case', contract_id: 7, case_type: 'advisor' })),
    ]
    for (const r of all) expect(r).not.toContain('/nonlit')
  })

  it('无合同的案件无处可去 → undefined（按未建页处理）', () => {
    expect(projectRoute(hit('projects', 11, { kind: 'case' }))).toBeUndefined()
  })
})
