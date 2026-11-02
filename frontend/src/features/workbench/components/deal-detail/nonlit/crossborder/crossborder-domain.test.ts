import { describe, expect, it } from 'vitest'

import { DEMO_NL2_CONTRACT, DEMO_NL2_FILTERS, DEMO_TH_CONTRACT_REVISIONS } from '../../demo-nonlit'
import {
  acceptedRevIds,
  alignClauses,
  filterRevisions,
  filterTabLabel,
  nextRevision,
  walkStats,
} from './crossborder-domain'

const tab = (id: string) => DEMO_NL2_FILTERS.find((t) => t.id === id)!

describe('filterTabLabel 筛选 tab 计数', () => {
  it('「全部」用修订总数，其余用自身口径条数', () => {
    expect(filterTabLabel(tab('all'), DEMO_TH_CONTRACT_REVISIONS.length)).toBe('全部 5')
    expect(filterTabLabel(tab('high'), DEMO_TH_CONTRACT_REVISIONS.length)).toBe('高 2')
    expect(filterTabLabel(tab('manual'), DEMO_TH_CONTRACT_REVISIONS.length)).toBe('需律师判断 1')
  })
})

describe('filterRevisions 按维度过滤', () => {
  it('全部：不过滤；高风险：只剩 r1/r2', () => {
    expect(filterRevisions(DEMO_TH_CONTRACT_REVISIONS, tab('all'))).toHaveLength(5)
    expect(filterRevisions(DEMO_TH_CONTRACT_REVISIONS, tab('high')).map((r) => r.id)).toEqual(['r1', 'r2'])
  })
  it('已挂法条 / 需律师判断 互不重叠', () => {
    const v = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, tab('verified')).map((r) => r.id)
    const m = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, tab('manual')).map((r) => r.id)
    expect(v).toEqual(['r1', 'r2', 'r3', 'r4'])
    expect(m).toEqual(['r5'])
    expect(v.filter((id) => m.includes(id))).toEqual([])
  })
  it('口径写错时不会把不相干的修订筛出来', () => {
    expect(filterRevisions(DEMO_TH_CONTRACT_REVISIONS, { id: 'x', label: '幽灵', revIds: ['nope'] })).toEqual([])
  })
})

describe('alignClauses 双栏对齐', () => {
  it('每句一行，左右段数相等', () => {
    const rows = alignClauses(DEMO_NL2_CONTRACT)
    expect(rows).toHaveLength(DEMO_NL2_CONTRACT.reduce((n, c) => n + c.sentences.length, 0))
    for (const r of rows) expect(r.en.length).toBe(r.zh.length)
  })
  it('修订句带上修订 id，非修订句不带', () => {
    const rows = alignClauses(DEMO_NL2_CONTRACT)
    expect(rows.find((r) => r.key === '2-1')?.rev).toBe('r1')
    expect(rows.find((r) => r.key === '1-0')?.rev).toBeUndefined()
  })
  it('左右段数不等时补空段，不让右栏错行', () => {
    const rows = alignClauses([
      {
        no: '9',
        titleEn: 'T',
        titleZh: '题',
        revs: ['r5'],
        sentences: [{ en: [{ text: 'a' }, { text: 'b', change: 'mod', rev: 'r5' }], zh: [{ text: '甲' }] }],
      },
    ])
    expect(rows[0]!.en).toHaveLength(2)
    expect(rows[0]!.zh).toEqual([{ text: '甲' }, { text: '' }])
  })
})

describe('逐条采纳推进', () => {
  const revs = DEMO_TH_CONTRACT_REVISIONS

  it('从第 1 条开始，处理过的跳过', () => {
    expect(nextRevision(revs, {})?.id).toBe('r1')
    expect(nextRevision(revs, { r1: 'accept' })?.id).toBe('r2')
    expect(nextRevision(revs, { r1: 'reject', r2: 'accept' })?.id).toBe('r3')
  })
  it('全部处理完 nextRevision 返回 null、walkStats 收尾', () => {
    const decided = Object.fromEntries(revs.map((r, i) => [r.id, i % 2 === 0 ? 'accept' : 'reject'])) as Record<
      string,
      'accept' | 'reject'
    >
    expect(nextRevision(revs, decided)).toBeNull()
    expect(walkStats(revs, decided)).toEqual({ accepted: 3, rejected: 2, done: true })
  })
  it('走一半不算完成', () => {
    expect(walkStats(revs, { r1: 'accept', r2: 'accept' })).toEqual({ accepted: 2, rejected: 0, done: false })
  })
  it('acceptedRevIds 只收采纳的', () => {
    expect(acceptedRevIds({ r1: 'accept', r2: 'reject', r3: 'accept' })).toEqual(['r1', 'r3'])
  })
})
