/**
 * 切段 / 并段 / 选页运算的**正文搬运**单测（P2-1）。
 *
 * 修前的行为：头段原样留着整段 md（含已切出去页的文字＝污染），尾段不带 md（＝丢失），
 * 被并段的 md 直接丢弃。这里锁住「每份正文只含自己那些页、并段不丢不重」，
 * 以及页锚点缺失时的兜底口径。全部用合成数据。
 */
import { describe, expect, it } from 'vitest'

import type { DraftState, PageSpan, PositionedBlock, Segment } from '../types'
import { mergeSegment, splitSegment } from './segments'
import { mergePagesIntoNew, mergeSegsIntoOne, splitOutPages } from './selection'

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

const PAGES = [
  { page: 1, text: '第一页：测试甲' },
  { page: 2, text: '第二页：测试乙' },
  { page: 3, text: '第三页：测试丙' },
]
const FULL = mdOfPages('证据材料', PAGES)

function segOf(over: Partial<Segment> = {}): Segment {
  return {
    id: 'seg-a',
    t: '',
    fn: '证据.pdf',
    refs: PAGES.map((p) => ({ mi: 0, p: p.page })),
    manual: false,
    md: FULL.md,
    pageSpans: FULL.spans,
    blocks: PAGES.map((p) => block(p.page, p.text)),
    ...over,
  }
}

function draft(segs: Segment[] = [segOf()]): DraftState {
  return {
    mats: [
      { partIndex: 0, n: '证据.pdf', k: 'pdf', pages: 3 },
      { partIndex: 1, n: '补充.pdf', k: 'pdf', pages: 2 },
    ],
    segs,
    infos: [],
  }
}

describe('splitSegment：正文按页分家', () => {
  it('头段只留自己的页 + 注入标题，尾段只含自己的页、不带旧段名', () => {
    const d = splitSegment(draft(), 0, 1)
    expect(d.segs[0]!.md).toBe('# 证据材料\n\n第一页：测试甲\n\n第二页：测试乙')
    expect(d.segs[1]!.md).toBe('第三页：测试丙')
    expect(d.segs[0]!.md).not.toContain('测试丙')
    expect(d.segs[1]!.md).not.toContain('测试甲')
  })

  it('定位块跟着页走，页锚点偏移按新 md 重算', () => {
    const d = splitSegment(draft(), 0, 1)
    expect(d.segs[0]!.blocks!.map((b) => b.page)).toEqual([1, 2])
    expect(d.segs[1]!.blocks!.map((b) => b.page)).toEqual([3])
    expect(d.segs[1]!.pageSpans).toEqual([{ page: 3, start: 0, end: '第三页：测试丙'.length }])
  })

  it('切/并都打 manualEdit.md：重跑识别不得静默覆盖律师整理过的正文', () => {
    const d = splitSegment(draft(), 0, 1)
    expect(d.segs[0]!.manualEdit).toMatchObject({ md: true })
    expect(d.segs[1]!.manualEdit).toMatchObject({ md: true })
    const back = mergeSegment(d, 1)
    expect(back.segs[0]!.manualEdit).toMatchObject({ md: true })
  })

  it('切开再并回：正文按页序复原，不丢不重', () => {
    const back = mergeSegment(splitSegment(draft(), 0, 1), 1)
    expect(back.segs[0]!.md).toBe(FULL.md)
    expect(back.segs[0]!.blocks!.map((b) => b.page)).toEqual([1, 2, 3])
    expect(back.segs[0]!.pageSpans).toEqual(FULL.spans)
  })

  it('无 pageSpans（旧任务）时按 blocks 页号近似切分', () => {
    const d = splitSegment(draft([segOf({ pageSpans: undefined })]), 0, 0)
    expect(d.segs[0]!.md).toBe('# 证据材料\n\n第一页：测试甲')
    expect(d.segs[1]!.md).toBe('第二页：测试乙\n\n第三页：测试丙')
  })

  it('既无 pageSpans 又无 blocks：整份正文留给头段，尾段宁可缺正文也不拿别页的字', () => {
    const d = splitSegment(draft([segOf({ pageSpans: undefined, blocks: undefined })]), 0, 1)
    expect(d.segs[0]!.md).toBe(FULL.md)
    expect(d.segs[1]!.md).toBeUndefined()
  })

  it('没有正文的段切开后不打 md 痕迹（没什么可保护）', () => {
    const d = splitSegment(draft([segOf({ md: undefined, pageSpans: undefined, blocks: undefined })]), 0, 1)
    expect(d.segs[0]!.manualEdit).toBeUndefined()
    expect(d.segs[1]!.manualEdit).toBeUndefined()
  })
})

describe('mergeSegment：被并段的正文不再丢弃', () => {
  it('两段各有正文时按页序拼接，注入标题只留一份', () => {
    const second = mdOfPages('补充材料', [{ page: 1, text: '补充第一页' }, { page: 2, text: '补充第二页' }])
    const d = draft([
      segOf(),
      segOf({
        id: 'seg-b',
        fn: '补充.pdf',
        refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }],
        md: second.md,
        pageSpans: second.spans,
        blocks: [block(1, '补充第一页'), block(2, '补充第二页')],
      }),
    ])
    const out = mergeSegment(d, 1)
    expect(out.segs).toHaveLength(1)
    expect(out.segs[0]!.md).toBe(`${FULL.md}\n\n补充第一页\n\n补充第二页`)
    expect(out.segs[0]!.md!.match(/# 证据材料/g)).toHaveLength(1)
    expect(out.segs[0]!.md).not.toContain('# 补充材料')
    expect(out.segs[0]!.blocks).toHaveLength(5)
  })

  it('无锚点时整份按段序拼接（不丢字），偏移未知则不带 pageSpans', () => {
    const d = draft([
      segOf({ pageSpans: undefined, blocks: undefined }),
      segOf({ id: 'seg-b', fn: '补充.pdf', refs: [{ mi: 1, p: 1 }], md: '补充正文', pageSpans: undefined, blocks: undefined }),
    ])
    const out = mergeSegment(d, 1)
    expect(out.segs[0]!.md).toBe(`${FULL.md}\n\n补充正文`)
    expect(out.segs[0]!.pageSpans).toBeUndefined()
  })
})

describe('splitOutPages：切出的页把正文带走', () => {
  it('中间页切出：头/中/尾三份各含自己的页，标题跟着原段首页走', () => {
    const d = splitOutPages(draft(), [{ mi: 0, p: 2 }])
    expect(d.segs).toHaveLength(3)
    expect(d.segs[0]!.md).toBe('# 证据材料\n\n第一页：测试甲')
    expect(d.segs[1]!.md).toBe('第二页：测试乙')
    expect(d.segs[2]!.md).toBe('第三页：测试丙')
    expect(d.segs[1]!.blocks!.map((b) => b.page)).toEqual([2])
    expect(d.segs.every((sg) => sg.manualEdit?.md)).toBe(true)
  })

  it('从首页切出：切出的那份带上注入标题，残段不带', () => {
    const d = splitOutPages(draft(), [{ mi: 0, p: 1 }])
    expect(d.segs[0]!.md).toBe('# 证据材料\n\n第一页：测试甲')
    expect(d.segs[1]!.md).toBe('第二页：测试乙\n\n第三页：测试丙')
  })

  it('无锚点时整份正文留给保住原段首页的那一份', () => {
    const bare = segOf({ pageSpans: undefined, blocks: undefined })
    const mid = splitOutPages(draft([bare]), [{ mi: 0, p: 2 }])
    expect(mid.segs[0]!.md).toBe(FULL.md)
    expect(mid.segs[1]!.md).toBeUndefined()
    expect(mid.segs[2]!.md).toBeUndefined()
    const head = splitOutPages(draft([bare]), [{ mi: 0, p: 1 }])
    expect(head.segs[0]!.md).toBe(FULL.md)
    expect(head.segs[1]!.md).toBeUndefined()
  })
})

describe('mergePagesIntoNew / mergeSegsIntoOne：跨段跨源搬运', () => {
  const second = mdOfPages('补充材料', [{ page: 1, text: '补充第一页' }, { page: 2, text: '补充第二页' }])
  const twoSegs = () => draft([
    segOf(),
    segOf({
      id: 'seg-b',
      fn: '补充.pdf',
      refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }],
      md: second.md,
      pageSpans: second.spans,
      blocks: [block(1, '补充第一页'), block(2, '补充第二页')],
    }),
  ])

  it('跨源选页并成一份：正文按页序拼接，两段的 P1 不串页', () => {
    const d = mergePagesIntoNew(twoSegs(), [{ mi: 0, p: 3 }, { mi: 1, p: 1 }])
    const merged = d.segs.find((sg) => sg.refs.some((r) => r.mi === 0) && sg.refs.some((r) => r.mi === 1))!
    expect(merged.md).toBe('第三页：测试丙\n\n补充第一页')
    expect(merged.blocks!.map((b) => b.text)).toEqual(['第三页：测试丙', '补充第一页'])
    expect(merged.manualEdit).toMatchObject({ md: true })
    // 残段只留自己剩下的页
    const restA = d.segs.find((sg) => sg.id === 'seg-a')!
    expect(restA.md).toBe('# 证据材料\n\n第一页：测试甲\n\n第二页：测试乙')
    const restB = d.segs.find((sg) => sg.id === 'seg-b')!
    expect(restB.md).toBe('补充第二页')
    expect(restB.pageSpans).toEqual([{ page: 2, start: 0, end: '补充第二页'.length }])
  })

  it('整段被搬走时（无锚点）正文跟着走，不留在空壳残段里', () => {
    const d = draft([
      segOf({ pageSpans: undefined, blocks: undefined }),
      segOf({ id: 'seg-b', fn: '补充.pdf', refs: [{ mi: 1, p: 1 }], md: '补充正文', pageSpans: undefined, blocks: undefined }),
    ])
    const out = mergePagesIntoNew(d, [{ mi: 1, p: 1 }])
    const merged = out.segs.find((sg) => sg.refs.some((r) => r.mi === 1))!
    expect(merged.md).toBe('补充正文')
    // 只被搬走部分页且无锚点：正文留在残段（宁可残段多带字，也不让新段拿别页正文）
    expect(out.segs.find((sg) => sg.id === 'seg-a')!.md).toBe(FULL.md)
  })

  it('多选段并成一份：正文按文档页序拼接，不丢不重', () => {
    const out = mergeSegsIntoOne(twoSegs(), [0, 1])
    expect(out.segs).toHaveLength(1)
    expect(out.segs[0]!.md).toBe(`${FULL.md}\n\n补充第一页\n\n补充第二页`)
    expect(out.segs[0]!.blocks).toHaveLength(5)
    expect(out.segs[0]!.manualEdit).toMatchObject({ md: true })
    expect(out.segs[0]!.pageSpans!.map((s) => s.page)).toEqual([1, 2, 3, 1, 2])
  })

  it('无锚点的多段合并：整份按段序拼接', () => {
    const d = draft([
      segOf({ pageSpans: undefined, blocks: undefined }),
      segOf({ id: 'seg-b', fn: '补充.pdf', refs: [{ mi: 1, p: 1 }], md: '补充正文', pageSpans: undefined, blocks: undefined }),
    ])
    const out = mergeSegsIntoOne(d, [0, 1])
    expect(out.segs[0]!.md).toBe(`${FULL.md}\n\n补充正文`)
    expect(out.segs[0]!.pageSpans).toBeUndefined()
  })
})
