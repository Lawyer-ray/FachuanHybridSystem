/**
 * 识别质量提示的纯逻辑单测。
 *
 * 这里锁的是「数据可能缺失」这条硬要求：旧任务的 summary 里没有 page_quality /
 * inconsistencies，后端也可能给缺字段的条目。收窄层必须把它们变成**明确的空**，
 * 而不是让 `undefined.filter(...)` 在渲染期炸掉阅读器。
 *
 * 页级质量（`page_quality`）的按源派生与落草稿在 `page-quality.test.ts`。
 */
import { describe, expect, it } from 'vitest'

import {
  docTypeLabel,
  inconsistencyKindOf,
  pagesText,
  qualityFlagLabel,
  reviewHintOf,
  readInconsistencies,
  readPageQuality,
  sortInconsistencies,
} from './quality'
import type { Inconsistency } from '../types'

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
    canonical: '测试甲',
    variant: '测试乙',
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
    expect(list[0]!.variant).toBe('测试乙')
    expect(list[1]!.pages).toEqual([])
    // 缺次数时按 0 兜底，不炸
    expect(list[1]!.variant_count).toBe(0)
  })

  /**
   * kind 是后端逐条新加的键。本函数是**逐键重建对象**，漏收 kind 就等于把它丢掉，
   * 抽屉永远看不到判据种类 → 姓名聚类被渲染成「疑似错字」（律师可能合并两个真人）。
   */
  it('kind 逐条透传（三种判据都保留），非字符串/缺失置 undefined', () => {
    const list = readInconsistencies([
      { ...good, kind: 'frequency' },
      { ...good, kind: 'entity_cluster', confidence: 'medium' },
      { ...good, kind: 'id_malformed', confidence: 'medium' },
      { ...good, kind: 1 },
      good,
    ])
    expect(list.map((x) => x.kind)).toEqual(['frequency', 'entity_cluster', 'id_malformed', undefined, undefined])
  })
})

describe('inconsistencyKindOf：判据种类收窄', () => {
  it('三种已知 kind 原样返回', () => {
    expect(inconsistencyKindOf({ kind: 'frequency' })).toBe('frequency')
    expect(inconsistencyKindOf({ kind: 'entity_cluster' })).toBe('entity_cluster')
    expect(inconsistencyKindOf({ kind: 'id_malformed' })).toBe('id_malformed')
  })

  it('缺失 / 空串 / 未知值一律按 frequency（旧任务产物与旧草稿没有该键）', () => {
    expect(inconsistencyKindOf({})).toBe('frequency')
    expect(inconsistencyKindOf({ kind: '' })).toBe('frequency')
    expect(inconsistencyKindOf({ kind: 'brand_new_kind' })).toBe('frequency')
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

/**
 * 段级复核：`review_flag` → 「要不要复核、为什么」。
 *
 * 这里锁两件事，都来自真实反馈（「那我怎么知道什么要复核」）：
 * 1. 只给「建议复核」四个字等于没说——原因必须写出来，且同一句话在中栏徽标、
 *    左栏 tooltip、右栏提示条三处必须**完全一致**（不一致会让律师不全信任何一处）；
 * 2. 拿不到原因时**不编**：宁可为空串，也不要给一句放之四海皆准的废话。
 */
describe('reviewHintOf：复核信号 → 人话', () => {
  it('正常段不出复核提示', () => {
    expect(reviewHintOf({ reviewFlag: 'normal' })).toBeNull()
    expect(reviewHintOf({})).toBeNull()
  })

  it('低置信度：原因按 source_method 分开说', () => {
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'layout_title', confidence: 0.5 })).toEqual({
      label: '建议复核',
      reason: '起点是按版面标题推断的，可能把上一份的末尾切进来 · 自动分段置信度 50%',
    })
    expect(
      reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'rule_adjacent_start', confidence: 0.55 })?.reason,
    ).toBe('和上一段的起点只隔一页，可能切得太碎 · 自动分段置信度 55%')
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'llm', confidence: 0.4 })?.reason).toBe(
      '模型对这一段的边界把握不大 · 自动分段置信度 40%',
    )
  })

  /**
   * 真实反馈：「置信度 90% 你还要我复核？」
   *
   * 90% 还打复核标记的情况是存在的（后端边界二审没能给出结论 → 打标记，但**刻意
   * 不动模型自报的置信度**，因为没有校准依据）。错在**我们把这个数字当成了理由**：
   * 提示里出现的百分比必须支持「要复核」这个结论，否则律师看到的就是一句自相矛盾
   * 的话，进而不再相信整个提示。
   */
  it('置信度不低时，不把百分比当理由：说清复核的是边界', () => {
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'llm', confidence: 0.9 })?.reason).toBe(
      '文字识别置信度 90%，要核对的是分段边界（二审没能给出结论）',
    )
    // 规则引擎的结构成因仍是真原因，但高置信度不再追加数字
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'layout_title', confidence: 0.9 })?.reason).toBe(
      '起点是按版面标题推断的，可能把上一份的末尾切进来',
    )
  })

  it('原因不明时不硬凑：只给置信度，不认识的方法一个字都不编', () => {
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'brand_new_method' })?.reason).toBe('')
    expect(reviewHintOf({ reviewFlag: 'low_confidence', sourceMethod: 'brand_new_method', confidence: 0.5 })?.reason).toBe(
      '自动分段置信度 50%',
    )
  })

  it('未识别 / OCR 失败各自有专属原因（不是同一句「建议复核」）', () => {
    expect(reviewHintOf({ reviewFlag: 'unrecognized' })).toEqual({
      label: '未识别',
      reason: '这一段没认出是哪类材料，可能是模板里没有的新类型',
    })
    expect(reviewHintOf({ reviewFlag: 'ocr_failed' })?.reason).toBe('这一段的文字没有取出来，正文可能是空的')
  })

  it('后端给了中文标签就用它（前端词表落后于后端时不会显示英文码）', () => {
    expect(reviewHintOf({ reviewFlag: 'low_confidence', reviewFlagLabel: '低置信度' })?.label).toBe('低置信度')
  })

  it('后端将来新增的取值：标签原样展示，原因留空（不编）', () => {
    expect(reviewHintOf({ reviewFlag: 'need_manual_merge' })).toEqual({ label: 'need_manual_merge', reason: '' })
  })
  it('两种切法不一致：陈述分歧并要求裁定，不暗示哪边对', () => {
    const hint = reviewHintOf({ reviewFlag: 'boundary_disagreement', sourceMethod: 'llm', confidence: 0.98 })
    expect(hint?.label).toBe('两种切法不一致')
    expect(hint?.reason).toContain('请核对这一段该不该从这一页开始')
    // 置信度 98% 不得被拿来当复核理由（写成「建议复核 · 置信度 98%」是自相矛盾）
    expect(hint?.reason).not.toContain('98%')
  })

})
