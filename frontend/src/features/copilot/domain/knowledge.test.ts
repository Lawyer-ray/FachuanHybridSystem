/**
 * 入站引用解析：`[Kn]` 的识别、与引用表的对齐、页号措辞。
 *
 * 这里的用例全部对准**误判成本**：多认一个方括号（把 `[1]` / `[2021]` 当来源）
 * 会让律师点开一个错来源，比少渲染一个角标严重得多。所以「不命中」的用例
 * 与「命中」的用例一样重要。
 */

import { describe, expect, it } from 'vitest'

import {
  hasPendingCiteMarker,
  pageSpanNote,
  parseCiteMarkers,
  reconcileCitations,
  splitCiteSegments,
  type CitationRef,
} from './knowledge'

/** 造一条最小可用引用；只覆盖用例关心的字段 */
function cite(citeNo: number, patch: Partial<CitationRef> = {}): CitationRef {
  return { citeNo, kind: 'file', name: `材料${citeNo}.pdf`, ...patch }
}

describe('parseCiteMarkers：只认 [K<数字>]', () => {
  it('`[K1]` 命中，并给出含方括号的下标', () => {
    const text = '结论见[K1]。'
    const marks = parseCiteMarkers(text)
    expect(marks).toEqual([{ citeNo: 1, start: 3, end: 7 }])
    // 下标必须能原样切回标记本身（渲染层靠它切片段）
    expect(text.slice(marks[0]?.start, marks[0]?.end)).toBe('[K1]')
  })

  it('一句话里多个标记按出现顺序给出', () => {
    expect(parseCiteMarkers('[K2]甲[K10]').map((m) => m.citeNo)).toEqual([2, 10])
  })

  it.each([
    ['列表序号 [1]', '第一条[1]'],
    ['法条年份 [2021]', '《民法典》自[2021]年起施行'],
    ['中文方括号【1】', '【1】判决如下'],
    ['全角圆括号（1）', '（1）本金'],
    ['空编号 [K]', '见[K]'],
    ['逗号编号 [K1,2]', '见[K1,2]'],
    ['小写 [k1]', '见[k1]'],
    ['超过三位 [K1234]', '见[K1234]'],
  ])('%s 不命中（宁可少渲染，也不能把法条年份变成来源）', (_label, text) => {
    expect(parseCiteMarkers(text)).toEqual([])
  })

  it('known 给了就只收其中的编号（模型乱标 [K9] 不渲染）', () => {
    const text = '见[K1]与[K9]'
    expect(parseCiteMarkers(text, new Set([1])).map((m) => m.citeNo)).toEqual([1])
    expect(parseCiteMarkers(text, new Set<number>())).toEqual([])
  })
})

describe('parseCiteMarkers：流式半截标记不命中', () => {
  it.each(['见[K', '见[K1', '见[K12'])('%j 不命中（等闭合的下一帧再包角标）', (text) => {
    expect(parseCiteMarkers(text)).toEqual([])
  })

  it('hasPendingCiteMarker 只认末尾的半截标记', () => {
    expect(hasPendingCiteMarker('结论见[K')).toBe(true)
    expect(hasPendingCiteMarker('结论见[K12')).toBe(true)
    // 已闭合 → 不是半截，正常渲染
    expect(hasPendingCiteMarker('结论见[K12]')).toBe(false)
    // 半截在中间（后面还有字）→ 不是「正在写」的状态，不降级
    expect(hasPendingCiteMarker('见[K，另见甲')).toBe(false)
    // 普通文本里恰好有 `[` 与 `K`，但不是标记
    expect(hasPendingCiteMarker('索引 [K 说明')).toBe(false)
  })
})

describe('reconcileCitations：正文没引用到的来源一律剔除', () => {
  it('只保留正文真的引用到的引用表项', () => {
    const result = reconcileCitations('结论见[K2]。', [cite(1), cite(2), cite(3)])
    expect(result.marks.map((m) => m.citeNo)).toEqual([2])
    expect(result.citations.map((c) => c.citeNo)).toEqual([2])
  })

  it('正文引用了引用表没有的编号 → 不产生标记，也不产生来源', () => {
    const result = reconcileCitations('见[K7]', [cite(1)])
    expect(result.marks).toEqual([])
    expect(result.citations).toEqual([])
  })

  it('引用表为空时正文原样保留（[K1] 当普通文本）', () => {
    expect(reconcileCitations('见[K1]', [])).toEqual({ marks: [], citations: [] })
  })
})

describe('splitCiteSegments：切「文字 / 角标」，拼回去一字不差', () => {
  it('切成 文字-角标-文字 三段', () => {
    expect(splitCiteSegments('甲[K1]乙')).toEqual([
      { kind: 'text', text: '甲' },
      { kind: 'cite', citeNo: 1 },
      { kind: 'text', text: '乙' },
    ])
  })

  it('没有标记时返回单段原文（渲染层据此跳过替换）', () => {
    expect(splitCiteSegments('没有任何标记')).toEqual([{ kind: 'text', text: '没有任何标记' }])
  })

  it('空串返回空数组（不塞一个空文本节点）', () => {
    expect(splitCiteSegments('')).toEqual([])
  })

  it('known 过滤掉的编号留在文字里，不丢字符', () => {
    const segments = splitCiteSegments('见[K1]与[K9]', new Set([1]))
    const text = segments.map((s) => (s.kind === 'text' ? s.text : '[K]')).join('')
    expect(segments.filter((s) => s.kind === 'cite')).toHaveLength(1)
    expect(text).toBe('见[K]与[K9]')
  })
})

describe('pageSpanNote：页号措辞必须区分 PDF 物理页与 docx 解析分段', () => {
  it('法条 / 裁判文书才敢说「第 N 页」', () => {
    expect(pageSpanNote(3, 'statute')).toBe('第 3 页')
    expect(pageSpanNote(3, 'judgment')).toBe('第 3 页')
  })

  it('材料文件说的是「第 N 段（按解析分段）」——说成页会让律师去翻纸质卷翻不到', () => {
    for (const kind of ['file', 'case', 'contract'] as const) {
      expect(pageSpanNote(3, kind)).toBe('第 3 段（按解析分段）')
      expect(pageSpanNote(3, kind)).not.toContain('页')
    }
  })

  it('两种措辞确实不同（回归：被改成统一文案时用例当场红）', () => {
    expect(pageSpanNote(5, 'file')).not.toBe(pageSpanNote(5, 'statute'))
  })
})
