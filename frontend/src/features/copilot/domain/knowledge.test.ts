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
  mergeCitations,
  narrowCitations,
  pageSpanNote,
  parseCiteMarkers,
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

describe('narrowCitations：线上 snake_case → 前端 camelCase（宁缺勿错）', () => {
  it('正常条目逐字段显式映射（缺的字段不凭空补）', () => {
    expect(
      narrowCitations([
        {
          cite_no: 2,
          kind: 'statute',
          ref_id: 31,
          name: '民法典第 577 条',
          page: 12,
          clause: '577',
          chunk_id: 8801,
          text: '当事人一方不履行合同义务…',
        },
      ]),
    ).toEqual([
      {
        citeNo: 2,
        kind: 'statute',
        refId: 31,
        name: '民法典第 577 条',
        page: 12,
        clause: '577',
        chunkId: 8801,
        text: '当事人一方不履行合同义务…',
      },
    ])
  })

  it('缺 cite_no 的条目整条丢弃（对不上角标的来源是毒药）', () => {
    expect(narrowCitations([{ name: '判决书.pdf', kind: 'judgment' }])).toEqual([])
  })

  it('缺 name（或空串 / 非字符串）的条目整条丢弃（不渲染空壳卡片）', () => {
    expect(narrowCitations([{ cite_no: 1, kind: 'file' }])).toEqual([])
    expect(narrowCitations([{ cite_no: 1, name: '', kind: 'file' }])).toEqual([])
    expect(narrowCitations([{ cite_no: 1, name: 42, kind: 'file' }])).toEqual([])
  })

  it('kind 不在闭集 → 落 file（种类只决定卡片字段，不值得丢整条）', () => {
    expect(narrowCitations([{ cite_no: 3, name: '某材料', kind: 'evidence' }])).toEqual([
      { citeNo: 3, kind: 'file', name: '某材料' },
    ])
    // 整个 kind 缺失同理（旧数据 / 后端未标注）
    expect(narrowCitations([{ cite_no: 3, name: '某材料' }])[0]?.kind).toBe('file')
  })

  it('多余字段被丢（不做泛型改键：raw 里未知键绝不带进渲染层）', () => {
    const [citation] = narrowCitations([
      // `refId` / `citeNo` 是**前端**键名，线上出现同名键不能反向覆盖映射结果
      { cite_no: 1, name: '合同.docx', kind: 'contract', refId: 999, citeNo: 77, debug_trace: 'x', score: 0.82 },
    ])
    expect(citation).toEqual({ citeNo: 1, kind: 'contract', name: '合同.docx' })
  })

  it('状不对（非数组 / null / 元素不是对象）→ 空数组，不抛', () => {
    expect(narrowCitations(undefined)).toEqual([])
    expect(narrowCitations(null)).toEqual([])
    expect(narrowCitations('citations')).toEqual([])
    expect(narrowCitations({ 0: { cite_no: 1, name: 'x' } })).toEqual([])
    expect(narrowCitations([null, 1, 'x', []])).toEqual([])
  })

  it('cite_no 非正整数（0 / 负数 / 小数 / 字符串数字）一律丢弃', () => {
    for (const citeNo of [0, -1, 1.5, '1', Number.NaN]) {
      expect(narrowCitations([{ cite_no: citeNo, name: '材料' }])).toEqual([])
    }
  })

  it('同 citeNo 后到为准，位置留在首次出现处（引用表不因补数据而跳位）', () => {
    const result = narrowCitations([
      { cite_no: 1, name: '先到的名字', page: 1 },
      { cite_no: 2, name: '另一条' },
      { cite_no: 1, name: '后到的名字', page: 9 },
    ])
    expect(result.map((c) => c.citeNo)).toEqual([1, 2])
    expect(result[0]).toEqual({ citeNo: 1, kind: 'file', name: '后到的名字', page: 9 })
  })

  it('顺序按线上给的原样保留（不按编号排序：编号是后端的叙述顺序）', () => {
    const result = narrowCitations([
      { cite_no: 3, name: 'c' },
      { cite_no: 1, name: 'a' },
      { cite_no: 2, name: 'b' },
    ])
    expect(result.map((c) => c.citeNo)).toEqual([3, 1, 2])
  })

  it('keywords 白名单：全字符串数组才收，混了非字符串/单串整体丢', () => {
    const keywordsOf = (keywords: unknown) =>
      narrowCitations([{ cite_no: 1, name: 'a', keywords }])[0]?.keywords
    expect(keywordsOf(['违约金', '解除'])).toEqual(['违约金', '解除'])
    // 混了非字符串：只留字符串（高亮差一个词不该丢整条来源）
    expect(keywordsOf(['违约金', 7])).toEqual(['违约金'])
    // 不是数组：整体不要，不做按空格切词那种瞎猜
    expect(keywordsOf('违约金')).toBeUndefined()
    expect(keywordsOf([7])).toBeUndefined()
  })
})

describe('mergeCitations：增量合并（citations 事件一轮可多次）', () => {
  it('已有为空时直接得到新的一批', () => {
    expect(mergeCitations(undefined, [cite(1)])).toEqual([cite(1)])
    expect(mergeCitations([], [])).toEqual([])
  })

  it('新编号追加在后，旧编号原位覆盖（后到为准）', () => {
    const merged = mergeCitations([cite(1, { name: '旧' }), cite(2)], [cite(1, { name: '新' }), cite(3)])
    expect(merged.map((c) => c.citeNo)).toEqual([1, 2, 3])
    expect(merged[0]?.name).toBe('新')
  })

  it('不改动入参（纯函数：store 里的旧引用表不被就地改写）', () => {
    const existing = [cite(1)]
    mergeCitations(existing, [cite(1, { name: '新' })])
    expect(existing[0]?.name).toBe('材料1.pdf')
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
