/**
 * 识别质量提示的纯逻辑单测。
 *
 * 这里锁的是「数据可能缺失」这条硬要求：旧任务的 summary 里没有 page_quality /
 * inconsistencies，后端也可能给缺字段的条目。收窄层必须把它们变成**明确的空**，
 * 而不是让 `undefined.filter(...)` 在渲染期炸掉阅读器。
 */
import { describe, expect, it } from 'vitest'

import {
  graphicPagesOf,
  pagesText,
  qualityFlagLabel,
  readInconsistencies,
  readPageQuality,
  sortInconsistencies,
  sparsePagesOf,
} from './quality'
import type { Inconsistency, Segment } from '../types'

function seg(refs: [number, number][]): Pick<Segment, 'refs'> {
  return { refs: refs.map(([mi, p]) => ({ mi, p })) }
}

describe('readPageQuality', () => {
  it('缺字段 / 非对象一律返回 null（旧任务没有这个键）', () => {
    expect(readPageQuality(undefined)).toBeNull()
    expect(readPageQuality(null)).toBeNull()
    expect(readPageQuality('oops')).toBeNull()
    expect(readPageQuality({})).toBeNull()
  })

  it('收窄三类页数组，剔除非数字', () => {
    const q = readPageQuality({
      graphic_pages: [147, '148', 150],
      sparse_pages: [149],
      blank_pages: [],
      details: { '147': '疑似图形页（图纸/印章/照片），请核对原图', '999': 42 },
    })
    expect(q?.graphic_pages).toEqual([147, 150])
    expect(q?.sparse_pages).toEqual([149])
    expect(q?.blank_pages).toEqual([])
    // 只保留字符串说明
    expect(q?.details).toEqual({ '147': '疑似图形页（图纸/印章/照片），请核对原图' })
  })

  it('三类页全空时返回 null（调用方少一层判断）', () => {
    expect(readPageQuality({ graphic_pages: [], sparse_pages: [], blank_pages: [] })).toBeNull()
  })
})

describe('readInconsistencies', () => {
  const good = {
    canonical: '罗向文',
    variant: '罗问文',
    canonical_count: 178,
    variant_count: 5,
    pages: [12, 45],
    confidence: 'high',
  }

  it('非数组 / 缺字段 / 两边同名都丢掉，好条目照常保留', () => {
    expect(readInconsistencies(undefined)).toEqual([])
    expect(readInconsistencies({})).toEqual([])
    const list = readInconsistencies([
      good,
      { canonical: '甲' }, // 缺 variant
      { canonical: '乙', variant: '乙' }, // 同名无意义
      { canonical: '丙', variant: '丁', pages: ['x'] }, // 页号非数字 → 空列表，条目仍留
    ])
    expect(list).toHaveLength(2)
    expect(list[0]!.variant).toBe('罗问文')
    expect(list[1]!.pages).toEqual([])
    // 缺次数时按 0 兜底，不炸
    expect(list[1]!.variant_count).toBe(0)
  })
})

describe('sortInconsistencies', () => {
  const mk = (over: Partial<Inconsistency>): Inconsistency => ({
    canonical: 'A',
    variant: 'B',
    canonical_count: 10,
    variant_count: 1,
    pages: [1],
    confidence: 'high',
    ...over,
  })

  it('high 在前，未知等级排最后；同级变体次数多的在前', () => {
    const sorted = sortInconsistencies([
      mk({ variant: 'low', confidence: '' }),
      mk({ variant: 'mid', confidence: 'medium' }),
      mk({ variant: 'high-many', variant_count: 5 }),
      mk({ variant: 'high-few', variant_count: 1 }),
    ])
    expect(sorted.map((x) => x.variant)).toEqual(['high-many', 'high-few', 'mid', 'low'])
  })

  it('不改原数组', () => {
    const list = [mk({ variant: 'b', confidence: '' }), mk({ variant: 'a' })]
    sortInconsistencies(list)
    expect(list.map((x) => x.variant)).toEqual(['b', 'a'])
  })
})

describe('graphicPagesOf / sparsePagesOf', () => {
  const quality = readPageQuality({ graphic_pages: [2, 147, 148], sparse_pages: [149], blank_pages: [] })

  it('按段内页序返回覆盖到的页，跨源重复页号按位置保留', () => {
    expect(graphicPagesOf(seg([[0, 1], [0, 2], [0, 3]]), quality)).toEqual([2])
    // 跨源合并段：两个源都有 P147，跳转需要两条都在
    expect(graphicPagesOf(seg([[0, 147], [1, 147]]), quality)).toEqual([147, 147])
  })

  it('没有质量数据 / seg 为空时返回空数组', () => {
    expect(graphicPagesOf(seg([[0, 1]]), null)).toEqual([])
    expect(graphicPagesOf(null, quality)).toEqual([])
    expect(sparsePagesOf(seg([[0, 1]]), quality)).toEqual([])
  })

  it('稀疏页单独取（图上的几个字 / 拍糊的一页）', () => {
    expect(sparsePagesOf(seg([[0, 149]]), quality)).toEqual([149])
  })
})

describe('qualityFlagLabel / pagesText', () => {
  it('已知标记翻成中文，未知标记原样显示不丢信息', () => {
    expect(qualityFlagLabel('graphic')).toBe('图形页')
    expect(qualityFlagLabel('sparse_text')).toBe('文字稀疏')
    expect(qualityFlagLabel('weird_flag')).toBe('weird_flag')
  })

  it('页号压成区间文案', () => {
    expect(pagesText([])).toBe('')
    expect(pagesText([147, 148])).toBe('P147–148')
    expect(pagesText([9, 3, 7, 8])).toBe('P3, P7–9')
  })
})
