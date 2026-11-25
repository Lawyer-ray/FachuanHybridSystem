/**
 * 识别质量提示的纯逻辑单测。
 *
 * 这里锁的是「数据可能缺失」这条硬要求：旧任务的 summary 里没有 page_quality /
 * inconsistencies，后端也可能给缺字段的条目。收窄层必须把它们变成**明确的空**，
 * 而不是让 `undefined.filter(...)` 在渲染期炸掉阅读器。
 */
import { describe, expect, it } from 'vitest'

import { withPageQuality } from './state'
import type { PageQuality } from '../types'

import {
  docHintPagesOf,
  docTodosOf,
  docTypeLabel,
  graphicPagesOf,
  inconsistencyKindOf,
  ocrFailedPagesOf,
  pagesText,
  qualityFlagLabel,
  reviewHintOf,
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

describe('ocrFailedPagesOf：取字失败的页必须能被单独告警', () => {
  // 回归 2026-11-25 材料包 617 的 p12：整页关键事实因为「一个字都没读到」
  // 被判成 blank，界面上只有一句「空白页」——律师会以为原件本来就没字。
  const quality = readPageQuality({ ocr_failed_pages: [12, 34], blank_pages: [7] })

  it('只有 ocr_failed_pages 也算「有质量数据」，不能返回 null', () => {
    expect(quality).not.toBeNull()
    expect(readPageQuality({ ocr_failed_pages: [12] })).not.toBeNull()
  })

  it('按段内页序返回覆盖到的失败页', () => {
    expect(ocrFailedPagesOf(seg([[0, 11], [0, 12], [0, 13]]), quality)).toEqual([12])
    expect(ocrFailedPagesOf(seg([[0, 12], [1, 12]]), quality)).toEqual([12, 12])
  })

  it('空白页不算取字失败（两者必须分开）', () => {
    expect(ocrFailedPagesOf(seg([[0, 7]]), quality)).toEqual([])
  })

  it('没有质量数据 / seg 为空时返回空数组', () => {
    expect(ocrFailedPagesOf(seg([[0, 12]]), null)).toEqual([])
    expect(ocrFailedPagesOf(null, quality)).toEqual([])
  })
})

describe('docHintPagesOf', () => {
  const quality = readPageQuality({
    doc_hints: { '23': 'id_card', '144': 'property_cert' },
    doc_missing: { '23': { doc: 'id_card', missing: ['姓名', '身份证号'] } },
  })

  it('按段内页序返回覆盖到的证件页，并带上该页缺失字段', () => {
    expect(docHintPagesOf(seg([[0, 22], [0, 23], [0, 144]]), quality)).toEqual([
      // p23 有缺失字段：调用方据此分档提示
      { page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
      // p144 没进 doc_missing：missing 给空数组，不臆造
      { page: 144, doc: 'property_cert', missing: [] },
    ])
    expect(docHintPagesOf(seg([[0, 23], [1, 23]]), quality)).toEqual([
      { page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
      { page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
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
})

/**
 * pageQuality 必须能落库（v27.16.8 修正）。
 *
 * 原先 `DraftStateToSave = Omit<DraftState, 'pageQuality'>`，理由是「落盘后会和
 * 律师后来的切段错位」。但那个担心代码里已经天然解决——`graphicPagesOf` 是拿
 * `seg.refs` 与 `quality.*_pages` **实时求交集**，段变了提示跟着变。
 * 而不落库的代价很实在：**刷新一次提示就没了**，得重新点「自动识别」才看得到，
 * 而这个功能的意义恰恰是「打开就知道哪页要核对」。
 */
describe('pageQuality 持久化契约', () => {
  it('withPageQuality 产出的字段经过 JSON 往返后完整保留', () => {
    const quality: PageQuality = {
      graphic_pages: [147, 148],
      sparse_pages: [23],
      blank_pages: [],
      details: { '147': '疑似图形页' },
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名', '身份证号'] } },
    }
    const draft = withPageQuality({ mats: [], segs: [], infos: [] } as never, quality)
    const roundTripped = JSON.parse(JSON.stringify(draft)) as { pageQuality?: PageQuality }

    expect(roundTripped.pageQuality).toEqual(quality)
  })

  it('切段后图形页标记跟着段走（证明持久化不会产生错位假提示）', () => {
    const quality: PageQuality = { graphic_pages: [147, 148] } as PageQuality
    // 原段覆盖 144-150，含两页图形页
    const wide = { refs: [144, 145, 146, 147, 148, 149, 150].map((p) => ({ mi: 0, p })) }
    // 拆一刀：只剩 144-146，图形页被划到另一段
    const narrow = { refs: [144, 145, 146].map((p) => ({ mi: 0, p })) }

    expect(graphicPagesOf(wide, quality)).toEqual([147, 148])
    expect(graphicPagesOf(narrow, quality)).toEqual([])
  })
})
