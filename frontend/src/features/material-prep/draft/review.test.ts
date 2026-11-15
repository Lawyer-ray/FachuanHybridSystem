/**
 * 复核清单数据层的单测：把四类信号归一成 `ReviewItem[]`。
 *
 * 这里锁三件在真实场景里必然出事的事：
 * 1. **只收本段的页**——164 页的卷宗被切成几十段，每段都拿到全卷清单的话，
 *    页头徽标会显示「本页 40 项」而抽屉里只有 2 项，律师就不信这个计数了；
 * 2. **id 与数组顺序无关**——后端重跑一次识别、顺序一换，按下标存的「已核对」
 *    就挂到别的条目上，律师会以为自己核对过；
 * 3. **旧任务/人工拆分缺信号不崩**——summary 里没有 page_quality、
 *    人工段没有 quality_flags 都是常态。
 */
import { describe, expect, it } from 'vitest'

import type {
  EngineDisagreement,
  Inconsistency,
  PageQuality,
  Segment,
} from '../types'
import {
  groupByPage,
  reviewItemId,
  reviewItemsOf,
  sortReviewItems,
  type ReviewItem,
} from './review'

/** 虚构的段落：refs 是本段覆盖的页（张三丰 / 武当山，纯属虚构） */
function seg(pageNos: number[], over: Partial<Segment> = {}): Segment {
  return {
    id: 'seg-1',
    t: '张三丰户口簿',
    fn: '张三丰户口簿.pdf',
    refs: pageNos.map((p, i) => ({ mi: 0, p: p === 0 ? i + 1 : p })),
    manual: false,
    ...over,
  }
}

function disagreement(over: Partial<EngineDisagreement> = {}): EngineDisagreement {
  return {
    page_no: 31,
    kind: 'char',
    severity: 'high',
    variants: [
      { engine: 'mineru', text: '曾妙焮' },
      { engine: 'paddleocr_vl', text: '曾妙焱' },
    ],
    context: '兹证明曾妙焮老师自2015年至今',
    anchor_hit: false,
    similarity: 0.66,
    ...over,
  }
}

function inconsistency(over: Partial<Inconsistency> = {}): Inconsistency {
  return {
    canonical: '武当山真武观',
    variant: '武当山真武宮',
    canonical_count: 12,
    variant_count: 2,
    pages: [31, 32],
    confidence: 'high',
    ...over,
  }
}

describe('reviewItemsOf：各信号源转换', () => {
  it('引擎分歧 → kind=disagreement，severity 与页号取自条目本身', () => {
    const items = reviewItemsOf(seg([31]), undefined, [disagreement()])
    expect(items).toHaveLength(1)
    const item = items[0]!
    expect(item.kind).toBe('disagreement')
    expect(item.severity).toBe('high')
    expect(item.page).toBe(31)
    expect(item.title).toBe('引擎分歧：曾妙焮 / 曾妙焱')
    // 原文片段用于正文批注定位，优先用截断原文
    expect(item.needle).toBe('兹证明曾妙焮老师自2015年至今')
    expect(item.anchor).toBe(false)
  })

  it('分歧自带 blocks 时取第一个非空 rect（零面积框不算）', () => {
    const items = reviewItemsOf(
      seg([31]),
      undefined,
      [
        disagreement({
          blocks: [
            {
              engine: 'mineru',
              page_no: 31,
              text: '曾妙焮',
              rect: { x: 0, y: 0, w: 0, h: 0 },
              block_type: 'text',
              approx: false,
            },
            {
              engine: 'paddleocr_vl',
              page_no: 31,
              text: '曾妙焱',
              rect: { x: 0.12, y: 0.44, w: 0.3, h: 0.04 },
              block_type: 'text',
              approx: false,
            },
          ],
        }),
      ],
    )
    // 只要坐标，不带 approx：画框只关心几何
    expect(items[0]!.rect).toEqual({ x: 0.12, y: 0.44, w: 0.3, h: 0.04 })
  })

  it('没有 blocks 的分歧不画框（rect 为 undefined）', () => {
    const items = reviewItemsOf(seg([31]), undefined, [disagreement()])
    expect(items[0]!.rect).toBeUndefined()
  })

  it('pageQuality.doc_missing → kind=doc_missing / high，缺字段名进标题', () => {
    const quality: PageQuality = {
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名', '身份证号'] } },
    }
    const items = reviewItemsOf(seg([23]), quality)
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      kind: 'doc_missing',
      severity: 'high',
      page: 23,
      title: '身份证缺字段：姓名、身份证号',
    })
  })

  it('doc_missing 的 missing 为空数组时仍是 high（整页可疑，不是「没问题」）', () => {
    const quality: PageQuality = {
      doc_hints: { '42': 'household' },
      doc_missing: { '42': { doc: 'household', missing: [] } },
    }
    const items = reviewItemsOf(seg([42]), quality)
    expect(items).toHaveLength(1)
    expect(items[0]!.severity).toBe('high')
    expect(items[0]!.title).toContain('整页内容可疑')
  })

  it('graphic_pages → graphic / medium，sparse_pages → sparse / low', () => {
    const quality: PageQuality = { graphic_pages: [147], sparse_pages: [149] }
    const items = reviewItemsOf(seg([147, 149]), quality)
    expect(items.map((i) => [i.kind, i.severity, i.page])).toEqual([
      ['graphic', 'medium', 147],
      ['sparse', 'low', 149],
    ])
  })

  it('页面有逐页说明时用它当标题（比前端硬编码文案具体）', () => {
    const quality: PageQuality = {
      graphic_pages: [147],
      details: { '147': '疑似图形页（宗地图），请核对原图' },
    }
    const items = reviewItemsOf(seg([147]), quality)
    expect(items[0]!.title).toBe('疑似图形页（宗地图），请核对原图')
  })

  it('inconsistencies → 每个页各一条 high（翻到第 32 页也要看得到）', () => {
    const items = reviewItemsOf(seg([31, 32]), undefined, undefined, [inconsistency()])
    expect(items.map((i) => [i.kind, i.severity, i.page])).toEqual([
      ['inconsistency', 'high', 31],
      ['inconsistency', 'high', 32],
    ])
    // needle 取疑似错字那个写法，正文批注要在 Markdown 里找它
    expect(items[0]!.needle).toBe('武当山真武宮')
  })

  it('seg.qualityFlags → quality / medium，挂在段首页', () => {
    const items = reviewItemsOf(seg([5, 6]), undefined, undefined, undefined)
    expect(items).toEqual([])
    const withFlags = reviewItemsOf(seg([5, 6], { qualityFlags: ['sparse_text'] }))
    expect(withFlags).toHaveLength(1)
    expect(withFlags[0]).toMatchObject({
      kind: 'quality',
      severity: 'medium',
      page: 5,
      // 未知/已知标记都过 qualityFlagLabel，中文统一
      title: '识别质量标记：文字稀疏',
    })
  })

  it('四类信号同时存在时全部归一，条数 = 各源之和', () => {
    const quality: PageQuality = {
      graphic_pages: [147],
      sparse_pages: [149],
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名'] } },
    }
    const items = reviewItemsOf(
      seg([23, 31, 147, 149], { qualityFlags: ['graphic'] }),
      quality,
      [disagreement()],
      [inconsistency()],
    )
    // 1 分歧 + 1 证件页 + 1 图形 + 1 稀疏 + 1 不一致(只 31 在段内) + 1 段标记
    expect(items).toHaveLength(6)
    expect(items.map((i) => i.kind).sort()).toEqual([
      'disagreement',
      'doc_missing',
      'graphic',
      'inconsistency',
      'quality',
      'sparse',
    ])
  })
})

describe('reviewItemsOf：只返回本段页范围内的项', () => {
  it('段外页的分歧 / 证件页 / 图纸页一律丢弃', () => {
    const quality: PageQuality = {
      graphic_pages: [147, 99],
      doc_hints: { '23': 'id_card', '88': 'id_card' },
      doc_missing: {
        '23': { doc: 'id_card', missing: ['姓名'] },
        '88': { doc: 'id_card', missing: ['住址'] },
      },
    }
    const items = reviewItemsOf(
      seg([23, 24]),
      quality,
      [disagreement({ page_no: 31 })],
      [inconsistency({ pages: [23, 31] })],
    )
    expect(items.map((i) => i.page).sort()).toEqual([23, 23])
    expect(items.every((i) => [23, 24].includes(i.page))).toBe(true)
  })

  it('refs 为空时返回空清单（删空页的段不能让下游炸）', () => {
    expect(reviewItemsOf(seg([]), { graphic_pages: [1] }, [disagreement({ page_no: 1 })])).toEqual(
      [],
    )
  })

  it('跨源合并段的重复页号只出一条（同一页不列两条一样的项）', () => {
    // refs 页号重复 = 跨源合并：mi 不同
    const merged: Segment = {
      id: 'seg-m',
      t: '合并段',
      fn: '合并段.pdf',
      refs: [
        { mi: 0, p: 147 },
        { mi: 1, p: 147 },
      ],
      manual: true,
    }
    const items = reviewItemsOf(merged, { graphic_pages: [147] })
    expect(items).toHaveLength(1)
  })
})

describe('reviewItemId：稳定性', () => {
  it('同内容 → 同 id；数组顺序变化不影响', () => {
    const a = reviewItemsOf(seg([31, 32]), undefined, undefined, [
      inconsistency({ pages: [31, 32] }),
    ])
    const b = reviewItemsOf(seg([32, 31]), undefined, undefined, [
      inconsistency({ pages: [32, 31] }),
    ])
    const idOfPage = (list: ReviewItem[], page: number) =>
      list.find((i) => i.page === page)!.id
    expect(idOfPage(a, 31)).toBe(idOfPage(b, 31))
    expect(idOfPage(a, 32)).toBe(idOfPage(b, 32))
  })

  it('分歧变体顺序互换后 id 不变（后端重跑会换顺序）', () => {
    const forward = reviewItemsOf(seg([31]), undefined, [
      disagreement({
        variants: [
          { engine: 'mineru', text: '张三丰' },
          { engine: 'paddleocr_vl', text: '張三丰' },
        ],
        context: '',
      }),
    ])
    const backward = reviewItemsOf(seg([31]), undefined, [
      disagreement({
        variants: [
          { engine: 'paddleocr_vl', text: '張三丰' },
          { engine: 'mineru', text: '张三丰' },
        ],
        context: '',
      }),
    ])
    expect(forward[0]!.id).toBe(backward[0]!.id)
  })

  it('内容不同 → id 不同（换了字的另一处分歧不能被当成已核对）', () => {
    const one = reviewItemsOf(seg([31]), undefined, [disagreement({ context: '甲方：张三丰' })])
    const two = reviewItemsOf(seg([31]), undefined, [disagreement({ context: '乙方：张三丰' })])
    expect(one[0]!.id).not.toBe(two[0]!.id)
  })

  it('id 形如 <短码>:<页号>:<内容>，不用数组下标', () => {
    const items = reviewItemsOf(
      seg([147]),
      { graphic_pages: [147] },
      [disagreement({ page_no: 147 })],
    )
    const graphic = items.find((i) => i.kind === 'graphic')!
    const dis = items.find((i) => i.kind === 'disagreement')!
    expect(graphic.id).toBe('graphic:147:图形页：请核对原图')
    // 前缀 + 页号 + 原文，可读、能排查「勾错了哪条」
    expect(dis.id.startsWith('dis:147:')).toBe(true)
    expect(dis.id).toContain('兹证明曾妙焮老师自2015年至今')
    // 同段同一页的图形页与分歧是两个独立条目，id 不会撞
    expect(graphic.id).not.toBe(dis.id)
  })

  it('直接调用 reviewItemId 与 reviewItemsOf 产出的 id 一致', () => {
    const item = reviewItemsOf(seg([23]), {
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名'] } },
    })[0]!
    const { id, ...rest } = item
    expect(reviewItemId(rest)).toBe(id)
  })
})

describe('sortReviewItems / groupByPage', () => {
  const items = reviewItemsOf(
    seg([23, 31, 147, 149, 12], { qualityFlags: ['graphic'] }),
    {
      graphic_pages: [147],
      sparse_pages: [149],
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名'] } },
    },
    [disagreement({ page_no: 31 })],
    [inconsistency({ pages: [12, 31] })],
  )

  it('severity 降序，同 severity 按页升序', () => {
    const sorted = sortReviewItems(items)
    const ranks = sorted.map((i) => ({ high: 0, medium: 1, low: 2 })[i.severity])
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b))
    // high 组内页升序
    const highPages = sorted.filter((i) => i.severity === 'high').map((i) => i.page)
    expect(highPages).toEqual([...highPages].sort((a, b) => a - b))
    // low 在最末
    expect(sorted[sorted.length - 1]!.severity).toBe('low')
  })

  it('排序是全序：同输入的两次排序结果一致（列表不会在律师眼前跳动）', () => {
    const once = sortReviewItems(items).map((i) => i.id)
    const twice = sortReviewItems([...items].reverse()).map((i) => i.id)
    expect(twice).toEqual(once)
  })

  it('不修改入参', () => {
    const copy = [...items]
    sortReviewItems(items)
    expect(items).toEqual(copy)
  })

  it('groupByPage：页升序，页内沿用 severity 降序', () => {
    const groups = groupByPage(items)
    const pages = groups.map((g) => g.page)
    expect(pages).toEqual([...pages].sort((a, b) => a - b))
    // 第 31 页上有分歧(high)与不一致(high)
    expect(groups.find((g) => g.page === 31)!.items.map((i) => i.kind).sort()).toEqual([
      'disagreement',
      'inconsistency',
    ])
    // 分组不丢项
    expect(groups.reduce((n, g) => n + g.items.length, 0)).toBe(items.length)
  })

  it('空输入不崩', () => {
    expect(sortReviewItems([])).toEqual([])
    expect(groupByPage([])).toEqual([])
  })
})

describe('缺信号不崩（旧任务 / 人工拆分）', () => {
  it('四个信号源全缺 → 空清单', () => {
    expect(reviewItemsOf(seg([1, 2]))).toEqual([])
    expect(reviewItemsOf(seg([1]), undefined, [], [])).toEqual([])
  })

  it('pageQuality 只有空数组 / 空字典 → 空清单', () => {
    expect(
      reviewItemsOf(seg([1]), { graphic_pages: [], sparse_pages: [], box_missing: [] } as PageQuality),
    ).toEqual([])
  })

  it('doc_missing 的键不是页号 → 丢弃，不影响同批其它页', () => {
    const quality: PageQuality = {
      doc_missing: {
        abc: { doc: 'id_card', missing: ['姓名'] },
        '0': { doc: 'id_card', missing: ['住址'] },
        '23': { doc: 'id_card', missing: ['性别'] },
      },
    }
    // seg([0]) 会被夹具改成 p=1，所以这里第 0 页本就不在段内；换用 1 号页验证坏键不污染
    const items = reviewItemsOf(seg([1, 23]), quality)
    expect(items.map((i) => i.page)).toEqual([23])
  })

  it('分歧缺严重度（脏数据）按 low 兜底，不丢整条', () => {
    const items = reviewItemsOf(seg([31]), undefined, [
      disagreement({ severity: 'weird' as never }),
    ])
    expect(items).toHaveLength(1)
    expect(items[0]!.severity).toBe('low')
  })

  it('分歧两个变体全为空串时不崩，标题仍说明是分歧', () => {
    const items = reviewItemsOf(seg([31]), undefined, [
      disagreement({
        variants: [
          { engine: 'mineru', text: '' },
          { engine: 'paddleocr_vl', text: '' },
        ],
        context: '',
      }),
    ])
    expect(items).toHaveLength(1)
    expect(items[0]!.title).toBe('引擎分歧')
    // 没有可用的文本，id 落到「短码:页号:标题」，仍然是内容决定的（不含下标）
    expect(items[0]!.id).toBe('dis:31:引擎分歧')
  })
})
