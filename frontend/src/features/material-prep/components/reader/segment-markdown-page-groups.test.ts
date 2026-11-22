/**
 * 正文面板的按页分组（从 SegmentMarkdown 抽出的纯逻辑）。
 *
 * 这里钉住两件会直接影响「读到哪一页就看到哪一页的问题」的事：
 * 1. 段外的分歧必须被丢掉（全卷口径传进来时会夹带别的页）；
 * 2. 落不到任何正文行的提示页要单独列出来（图纸页往往一个字都没取出来）。
 */
import { describe, expect, it } from 'vitest'

import type { EngineDisagreement } from '../../types'
import type { DocHintPage } from './SegmentQualityHint'
import { groupDisagreementsByPage, groupDocHintsByPage } from './segment-markdown-page-groups'

function dis(page_no: number, context = '示例'): EngineDisagreement {
  return {
    page_no,
    kind: 'char',
    severity: 'high',
    variants: [],
    context,
    anchor_hit: false,
    similarity: 0.5,
  }
}

describe('groupDisagreementsByPage：按页挂、段外的丢掉', () => {
  it('同页多条进同一个桶，keys 与 items 一一对应', () => {
    const byPage = groupDisagreementsByPage({
      engineItems: [dis(3, '甲'), dis(3, '乙'), dis(5, '丙')],
      engineKeys: ['k1', 'k2', 'k3'],
      pageNos: [3, 4, 5],
    })
    expect([...byPage.keys()]).toEqual([3, 5])
    expect(byPage.get(3)!.keys).toEqual(['k1', 'k2'])
    expect(byPage.get(3)!.items.map((d) => d.context)).toEqual(['甲', '乙'])
    expect(byPage.get(5)!.keys).toEqual(['k3'])
  })

  it('不在本段页范围里的分歧被丢弃（否则读 P3 时冒出 P9 的分歧）', () => {
    const byPage = groupDisagreementsByPage({
      engineItems: [dis(3), dis(9)],
      engineKeys: ['k1', 'k2'],
      pageNos: [3],
    })
    expect([...byPage.keys()]).toEqual([3])
  })

  it('缺唯一键的那一条跳过（没有键就挂不上勾选与高亮）', () => {
    const byPage = groupDisagreementsByPage({
      engineItems: [dis(3, '甲'), dis(3, '乙')],
      engineKeys: ['k1'],
      pageNos: [3],
    })
    expect(byPage.get(3)!.keys).toEqual(['k1'])
    expect(byPage.get(3)!.items).toHaveLength(1)
  })
})

describe('groupDocHintsByPage：证件页 / 图纸页提示落到哪一页', () => {
  const docPages: DocHintPage[] = [
    { page: 2, doc: 'id_card', missing: ['有效期'] },
    { page: 2, doc: 'license' },
    { page: 7, doc: 'license' },
  ]

  it('同页证件提示只取第一条（一页一条提示，不叠成两条）', () => {
    const g = groupDocHintsByPage({ docPages, graphicPages: [], blocks: [{ page: 2 }] })
    expect(g.docByPage.get(2)!.doc).toBe('id_card')
    expect(g.hintedPages).toEqual([2, 7])
  })

  it('有提示但没有任何正文行的页 → orphanHintPages（图纸页多半如此）', () => {
    const g = groupDocHintsByPage({
      docPages,
      graphicPages: [4],
      blocks: [{ page: 2 }, { page: 2 }, { page: 7 }],
    })
    expect(g.orphanHintPages).toEqual([4])
    expect(g.graphicPages.has(4)).toBe(true)
  })

  it('有正文行的页不算孤立；页号升序且去重（证件页与图纸页同页只算一次）', () => {
    const g = groupDocHintsByPage({
      docPages: [{ page: 5, doc: 'license' }],
      graphicPages: [5, 1],
      blocks: [{ page: 5 }],
    })
    expect(g.hintedPages).toEqual([1, 5])
    expect(g.orphanHintPages).toEqual([1])
  })
})
