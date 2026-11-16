/**
 * 页锚点搬运正文（md-pages）纯逻辑单测。
 *
 * 锁的是三件事：① 切/并段后每份正文只含自己那些页；② 块级编辑定位到**本页第 n 次**
 * 出现而不是全段首次匹配（印章核验语每页重复，首次匹配会改到别页）；③ 锚不到时
 * 返回 null/-1 让调用方显式兜底，不静默漂移。全部用合成数据。
 */
import { describe, expect, it } from 'vitest'

import type { PageSpan, PositionedBlock, Segment } from '../types'
import {
  blockTextIndexOf,
  blocksForPages,
  joinMdByPages,
  normalizePageSpans,
  pageRegionOf,
  pageSpansOf,
  shiftPageSpans,
} from './md-pages'

/** 按后端 build_segment_markdown 的口径造 md：`# 段名` + 各页正文，页间 `\n\n` */
function mdOfPages(title: string, pages: { page: number; text: string }[]): { md: string; spans: PageSpan[] } {
  const md = [`# ${title}`, ...pages.map((p) => p.text)].join('\n\n')
  let cursor = md.indexOf('\n\n') + 2
  const spans = pages.map((p) => {
    const start = md.indexOf(p.text, cursor)
    cursor = start + p.text.length
    return { page: p.page, start, end: cursor }
  })
  return { md, spans }
}

function block(page: number, text: string): PositionedBlock {
  return { page, type: 'text', text, rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' } }
}

function seg(over: Partial<Segment> = {}): Segment {
  return { id: 's1', t: '', fn: '借款合同', refs: [{ mi: 0, p: 1 }], manual: false, ...over }
}

const twoPages = mdOfPages('借款合同', [
  { page: 1, text: '甲方：测试甲\n第一条 借款金额 100 元' },
  { page: 2, text: '乙方：测试乙\n第二条 还款日期 2026 年 1 月' },
])

describe('normalizePageSpans：后端锚点收窄', () => {
  it('合法锚点按 start 升序返回（后端给的顺序不保证）', () => {
    const raw = [twoPages.spans[1], twoPages.spans[0]]
    expect(normalizePageSpans(raw, twoPages.md.length)).toEqual(twoPages.spans)
  })

  it('越界 / 非整数 / 页号非法 / end<=start 一律剔除，全非法返回 null', () => {
    const good = twoPages.spans[0]!
    const bad = [
      { page: 1, start: -1, end: 5 },
      { page: 1, start: 0, end: twoPages.md.length + 1 },
      { page: 0, start: 0, end: 5 },
      { page: 1, start: 5, end: 5 },
      { page: 1, start: 1.5, end: 6 },
      { page: 1, start: '0', end: 5 },
      null,
      'x',
    ]
    expect(normalizePageSpans([good, ...bad], twoPages.md.length)).toEqual([good])
    expect(normalizePageSpans(bad, twoPages.md.length)).toBeNull()
    expect(normalizePageSpans(undefined, 10)).toBeNull()
    expect(normalizePageSpans([], 10)).toBeNull()
  })
})

describe('pageSpansOf：精确锚点优先，blocks 近似兜底', () => {
  it('有 pageSpans 就用它（blocks 也在也不受影响）', () => {
    const s = seg({ md: twoPages.md, pageSpans: twoPages.spans, blocks: [block(1, '甲方：测试甲')] })
    expect(pageSpansOf(s)).toEqual(twoPages.spans)
    expect(pageRegionOf(s, 2)).toEqual({ start: twoPages.spans[1]!.start, end: twoPages.spans[1]!.end })
  })

  it('pageSpans 非法时退到 blocks 近似，而不是按错偏移切', () => {
    const s = seg({
      md: twoPages.md,
      pageSpans: [{ page: 1, start: 0, end: 9999 }],
      blocks: [block(1, '甲方：测试甲'), block(2, '乙方：测试乙')],
    })
    const spans = pageSpansOf(s)!
    expect(spans.map((x) => x.page)).toEqual([1, 2])
    expect(twoPages.md.slice(spans[0]!.start, spans[0]!.end)).toContain('第一条')
    expect(twoPages.md.slice(spans[1]!.start, spans[1]!.end)).toContain('第二条')
  })

  it('表格块文字与 md 的 GFM 对不上时，按页界圈范围仍把整页正文带上', () => {
    const md = '# 流水\n\n| 日期 | 金额 |\n| --- | --- |\n| 20260101 | 100 |\n\n下一页正文'
    const s = seg({
      md,
      refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }],
      // 表格块的原文是引擎侧的 HTML/纯文本，md 里已被重排成 GFM → 整块匹配必然失败
      blocks: [block(1, '日期 金额 20260101 100'), block(2, '下一页正文')],
    })
    const spans = pageSpansOf(s)!
    expect(spans).toHaveLength(2)
    expect(md.slice(spans[0]!.start, spans[0]!.end)).toContain('| 20260101 | 100 |')
    expect(md.slice(spans[1]!.start, spans[1]!.end)).toBe('下一页正文')
  })

  it('既无 pageSpans 又无 blocks / 无正文：返回 null（调用方必须显式兜底）', () => {
    expect(pageSpansOf(seg({ md: twoPages.md }))).toBeNull()
    expect(pageSpansOf(seg({ blocks: [block(1, '甲方：测试甲')] }))).toBeNull()
    expect(pageSpansOf(seg())).toBeNull()
    expect(pageRegionOf(seg({ md: twoPages.md }), 9)).toBeNull()
  })
})

describe('blockTextIndexOf：页区间 + 同页同文序号', () => {
  const stamp = '已核对与原件相符'
  const md = `# 核验\n\n${stamp}\n正文一\n${stamp}\n\n第二页\n${stamp}`
  const s = seg({
    md,
    refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }],
    blocks: [block(1, stamp), block(1, '正文一'), block(1, stamp), block(2, stamp)],
    pageSpans: [
      { page: 1, start: md.indexOf(stamp), end: md.indexOf('\n\n第二页') },
      { page: 2, start: md.indexOf('第二页'), end: md.length },
    ],
  })

  it('同页重复文字按块序取第 n 次出现（不是全段首次匹配）', () => {
    expect(blockTextIndexOf(s, 0, stamp)).toBe(md.indexOf(stamp))
    expect(blockTextIndexOf(s, 2, stamp)).toBe(md.indexOf(stamp, md.indexOf(stamp) + 1))
  })

  it('跨页同文只在本页区间内找：第二页的块不会命中第一页', () => {
    const at = blockTextIndexOf(s, 3, stamp)
    expect(at).toBe(md.lastIndexOf(stamp))
    expect(at).toBeGreaterThan(md.indexOf('第二页'))
  })

  it('锚不到 / 匹配超出本页区间 / 空原文：返回 -1', () => {
    expect(blockTextIndexOf(s, 1, '正文一')).toBe(md.indexOf('正文一'))
    expect(blockTextIndexOf(s, 0, '完全不存在的文字')).toBe(-1)
    expect(blockTextIndexOf(s, 0, '')).toBe(-1)
    expect(blockTextIndexOf(seg({ md: '正文' }), 0, '正文')).toBe(-1)
    // 第一页只有两处 stamp，第三处落在第二页 → 超出本页区间即视为锚不到
    const few = seg({ ...s, blocks: [block(1, stamp), block(1, stamp), block(1, stamp)] })
    expect(blockTextIndexOf(few, 2, stamp)).toBe(-1)
  })
})

describe('shiftPageSpans：正文局部替换后平移偏移', () => {
  const spans: PageSpan[] = [
    { page: 1, start: 10, end: 20 },
    { page: 2, start: 22, end: 30 },
  ]

  it('改动点之前不动、之后整体平移、含改动点的那页只改 end', () => {
    expect(shiftPageSpans(spans, 12, 2, 5)).toEqual([
      { page: 1, start: 10, end: 23 },
      { page: 2, start: 25, end: 33 },
    ])
    // 缩短同样成立
    expect(shiftPageSpans(spans, 24, 4, 1)).toEqual([
      { page: 1, start: 10, end: 20 },
      { page: 2, start: 22, end: 27 },
    ])
  })
})

describe('joinMdByPages：按页归属搬运正文', () => {
  const s = seg({
    md: twoPages.md,
    pageSpans: twoPages.spans,
    refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }],
    blocks: [block(1, '甲方：测试甲'), block(2, '乙方：测试乙')],
  })

  it('切段：头段带注入标题且只含自己的页，尾段不带旧段名', () => {
    const head = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 1 }] }], true)!
    const tail = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 2 }] }])!
    expect(head.md).toBe('# 借款合同\n\n甲方：测试甲\n第一条 借款金额 100 元')
    expect(tail.md).toBe('乙方：测试乙\n第二条 还款日期 2026 年 1 月')
    expect(tail.md).not.toContain('借款合同')
    expect(tail.md).not.toContain('测试甲')
  })

  it('搬完的页锚点偏移相对新 md 重算（不是照抄旧偏移）', () => {
    const tail = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 2 }] }])!
    expect(tail.pageSpans).toEqual([{ page: 2, start: 0, end: tail.md.length }])
    const head = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 1 }] }], true)!
    expect(head.md.slice(head.pageSpans[0]!.start, head.pageSpans[0]!.end)).toBe('甲方：测试甲\n第一条 借款金额 100 元')
  })

  it('页序由传入的 pages 决定（并段后按页序拼接，不重不丢）', () => {
    const out = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 2 }, { mi: 0, p: 1 }] }], true)!
    expect(out.md.indexOf('测试乙')).toBeLessThan(out.md.indexOf('测试甲'))
    expect(out.pageSpans.map((x) => x.page)).toEqual([2, 1])
    // 重复页只取一次
    const dup = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 1 }, { mi: 0, p: 1 }] }])!
    expect(dup.pageSpans).toHaveLength(1)
  })

  it('跨源合并：两段都有 P1，按段分开取不串页', () => {
    const a = mdOfPages('材料一', [{ page: 1, text: '测试甲的第一页' }])
    const b = mdOfPages('材料二', [{ page: 1, text: '测试乙的第一页' }])
    const out = joinMdByPages([
      { seg: seg({ id: 'a', md: a.md, pageSpans: a.spans }), pages: [{ mi: 0, p: 1 }] },
      { seg: seg({ id: 'b', md: b.md, pageSpans: b.spans }), pages: [{ mi: 1, p: 1 }] },
    ], true)!
    expect(out.md).toBe('# 材料一\n\n测试甲的第一页\n\n测试乙的第一页')
    expect(out.pageSpans).toHaveLength(2)
    expect(out.md.slice(out.pageSpans[1]!.start, out.pageSpans[1]!.end)).toBe('测试乙的第一页')
  })

  it('任一段锚不到页就整体返回 null（半精确拼接会静默丢字）', () => {
    expect(joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 1 }] }, { seg: seg({ id: 'x', md: '无锚点正文' }), pages: [{ mi: 1, p: 1 }] }])).toBeNull()
    expect(joinMdByPages([])).toEqual({ md: '', pageSpans: [] })
  })

  it('没有该页锚点时不硬塞别页正文（宁可少，不可错）', () => {
    const out = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 9 }] }])!
    expect(out.md).toBe('')
    expect(out.pageSpans).toEqual([])
  })
})

describe('blocksForPages：定位块按页号分家', () => {
  const blocks = [block(1, '一'), block(3, '三'), block(7, '七')]

  it('refs 跳号也按页号匹配（不能用「页号-起始页」当下标）', () => {
    expect(blocksForPages(blocks, [{ mi: 0, p: 3 }, { mi: 0, p: 7 }])).toEqual([blocks[1], blocks[2]])
  })

  it('无块 / 无命中页返回 undefined（不留空数组）', () => {
    expect(blocksForPages(undefined, [{ mi: 0, p: 1 }])).toBeUndefined()
    expect(blocksForPages(blocks, [{ mi: 0, p: 9 }])).toBeUndefined()
  })
})

/**
 * 后端 `_assemble_segment` 把跨页续表合并时用的是 `\n`（不是 `\n\n`）。
 * 搬运正文时硬塞空行会把一张表拆成两张——续表行丢掉表头，金额/日期就错列了。
 */
describe('joinMdByPages：沿用源 md 的页间分隔符', () => {
  const row1 = '| 20260101 | 100 |'
  const row2 = '| 20260102 | 200 |'
  const md = `# 流水\n\n| 日期 | 金额 |\n| --- | --- |\n${row1}\n${row2}\n\n备注：测试甲`
  const s = seg({
    md,
    refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }, { mi: 0, p: 3 }],
    pageSpans: [
      { page: 1, start: md.indexOf('| 日期'), end: md.indexOf(row1) + row1.length },
      { page: 2, start: md.indexOf(row2), end: md.indexOf(row2) + row2.length },
      { page: 3, start: md.indexOf('备注'), end: md.length },
    ],
  })

  it('续表两页拼回一张表（中间仍是单换行）', () => {
    const out = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }] }], true)!
    expect(out.md).toBe(`# 流水\n\n| 日期 | 金额 |\n| --- | --- |\n${row1}\n${row2}`)
  })

  it('非续表的页间仍是空行；搬完的锚点仍能切出原文', () => {
    const out = joinMdByPages([{ seg: s, pages: s.refs }], true)!
    expect(out.md).toBe(md)
    expect(out.md.slice(out.pageSpans[1]!.start, out.pageSpans[1]!.end)).toBe(row2)
  })

  it('倒序取页时不沿用分隔符（不能把两块正文粘成一行）', () => {
    const out = joinMdByPages([{ seg: s, pages: [{ mi: 0, p: 2 }, { mi: 0, p: 1 }] }])!
    expect(out.md).toBe(`${row2}\n\n| 日期 | 金额 |\n| --- | --- |\n${row1}`)
  })
})
