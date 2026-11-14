/**
 * 识别质量提示的纯逻辑单测。
 *
 * 这里锁的是「数据可能缺失」这条硬要求：旧任务的 summary 里没有 page_quality /
 * inconsistencies，后端也可能给缺字段的条目。收窄层必须把它们变成**明确的空**，
 * 而不是让 `undefined.filter(...)` 在渲染期炸掉阅读器。
 */
import { describe, expect, it } from 'vitest'

import {
  docHintPagesOf,
  docTodosOf,
  docTypeLabel,
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

  it('收窄 doc_hints：只留非空字符串，页号键原样保留', () => {
    const q = readPageQuality({
      graphic_pages: [],
      doc_hints: { '23': 'id_card', '42': '', '99': 7 },
    })
    expect(q?.doc_hints).toEqual({ '23': 'id_card' })
  })

  it('只有 doc_hints 也算「有质量数据」，不再返回 null', () => {
    const q = readPageQuality({ doc_hints: { '23': 'id_card' } })
    expect(q).not.toBeNull()
    expect(q?.doc_hints).toEqual({ '23': 'id_card' })
  })

  it('收窄 doc_missing：坏条目丢掉，missing 里非字符串剔除', () => {
    const q = readPageQuality({
      doc_hints: { '23': 'id_card' },
      doc_missing: {
        '23': { doc: 'id_card', missing: ['姓名', '', 42, '身份证号'] },
        '42': { doc: 'id_card', missing: [] }, // 字段都在但内容可疑 → 保留
        '77': 'oops',
      },
    })
    expect(q?.doc_missing).toEqual({
      '23': { doc: 'id_card', missing: ['姓名', '身份证号'] },
      '42': { doc: 'id_card', missing: [] },
    })
  })

  it('只有 doc_missing 也算有数据（单独出现时不丢）', () => {
    const q = readPageQuality({ doc_missing: { '23': { doc: 'id_card', missing: ['姓名'] } } })
    expect(q).not.toBeNull()
    expect(q?.doc_missing).toEqual({ '23': { doc: 'id_card', missing: ['姓名'] } })
  })

  it('旧任务完全没有 doc_hints / doc_missing 时这两个键是空对象，不崩', () => {
    const q = readPageQuality({ graphic_pages: [1] })
    expect(q?.doc_hints).toEqual({})
    expect(q?.doc_missing).toEqual({})
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

describe('docHintPagesOf', () => {
  const quality = readPageQuality({ doc_hints: { '23': 'id_card', '144': 'property_cert' } })

  it('按段内页序返回覆盖到的证件页，跨源重复页号按位置保留', () => {
    expect(docHintPagesOf(seg([[0, 22], [0, 23], [0, 144]]), quality)).toEqual([
      { page: 23, doc: 'id_card' },
      { page: 144, doc: 'property_cert' },
    ])
    expect(docHintPagesOf(seg([[0, 23], [1, 23]]), quality)).toEqual([
      { page: 23, doc: 'id_card' },
      { page: 23, doc: 'id_card' },
    ])
  })

  it('没有证件数据 / seg 为空时返回空数组', () => {
    expect(docHintPagesOf(seg([[0, 23]]), null)).toEqual([])
    expect(docHintPagesOf(null, quality)).toEqual([])
    // 只有图纸页数据（旧任务）时也返回空
    expect(docHintPagesOf(seg([[0, 147]]), readPageQuality({ graphic_pages: [147] }))).toEqual([])
  })
})

describe('docTypeLabel', () => {
  it('已知类型码翻成中文，未知码原样显示不丢信息', () => {
    expect(docTypeLabel('id_card')).toBe('身份证')
    expect(docTypeLabel('property_cert')).toBe('不动产权证')
    expect(docTypeLabel('bank_statement')).toBe('bank_statement')
  })

  /**
   * 锁住与后端 `doc_type._DOC_LABELS` 逐字一致。
   *
   * 漏掉这一条时踩过：「marriage」前端叫「婚姻状况证明」、后端叫「结婚证」——
   * 同一个证件在两处叫两个名字，律师会以为是两样材料。
   */
  it('六个类型码的中文名与后端 _DOC_LABELS 完全一致', () => {
    expect({
      id_card: docTypeLabel('id_card'),
      household: docTypeLabel('household'),
      marriage: docTypeLabel('marriage'),
      property_cert: docTypeLabel('property_cert'),
      license: docTypeLabel('license'),
      income_proof: docTypeLabel('income_proof'),
    }).toEqual({
      id_card: '身份证',
      household: '户口簿',
      marriage: '结婚证',
      property_cert: '不动产权证',
      license: '营业执照',
      income_proof: '收入证明',
    })
  })
})

describe('docTodosOf', () => {
  const quality = readPageQuality({
    doc_hints: { '23': 'id_card', '42': 'id_card', '144': 'property_cert', '8': 'license' },
    doc_missing: {
      '23': { doc: 'id_card', missing: ['姓名', '身份证号', '住址'] },
      // 字段都在但内容可疑（乱码 / 拍糊）：missing 为空数组，但仍要进清单
      '42': { doc: 'id_card', missing: [] },
      '144': { doc: 'property_cert', missing: ['权证号'] },
      // '8' 有 doc_hint 但不在 doc_missing 里（识别得干净）→ 不进清单
    },
  })

  it('按缺失字段数量降序，数量相同按页号', () => {
    expect(docTodosOf(quality).map((t) => t.page)).toEqual([23, 144, 42])
  })

  it('每条带页号、证件中文名、缺的字段', () => {
    const [first, second, third] = docTodosOf(quality)
    expect(first).toMatchObject({ page: 23, doc: 'id_card', label: '身份证', missing: ['姓名', '身份证号', '住址'] })
    expect(second).toMatchObject({ page: 144, label: '不动产权证', missing: ['权证号'] })
    // 字段都在但内容可疑的页仍然进清单，只是 missing 为空数组
    expect(third).toMatchObject({ page: 42, missing: [] })
  })

  it('不在 doc_missing 里的证件页不进清单（识别干净，律师无需补录）', () => {
    expect(docTodosOf(quality).some((t) => t.page === 8)).toBe(false)
  })

  it('doc_missing 带了类型而 doc_hints 没说时，用 doc_missing 的类型', () => {
    const q = readPageQuality({ doc_missing: { '5': { doc: 'household', missing: ['姓名'] } } })
    expect(docTodosOf(q)[0]).toMatchObject({ page: 5, label: '户口簿' })
  })

  it('类型完全缺失时按「证件页」兜底，不渲染空标签', () => {
    const q = readPageQuality({ doc_missing: { '5': { missing: ['姓名'] } } })
    expect(docTodosOf(q)[0]).toMatchObject({ page: 5, doc: '', label: '证件页' })
  })

  it('旧任务没有数据时返回空清单', () => {
    expect(docTodosOf(null)).toEqual([])
    expect(docTodosOf(readPageQuality({ graphic_pages: [147] }))).toEqual([])
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
