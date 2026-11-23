/**
 * 「识别错了怎么办」的两个纯函数：改正文、删错框。
 *
 * 这两件事必须分开：框画歪 ≠ 文字读错。删框不能把正文一起弄没了，
 * 改正文也不该顺手把定位块清空。
 */
import { describe, expect, it } from 'vitest'

import { blockKeyOf } from './block-keys'
import { detectAutoSplitConflicts } from './auto-split'
import { removeSegmentBlock, setSegmentBlockText, setSegmentMarkdown } from './segments'
import type { DraftState, PdfSplitSegmentSuggestion, PositionedBlock, Segment } from '../types'

function seg(over: Partial<Segment> = {}): Segment {
  return { id: 's1', t: '', fn: '证据一', refs: [{ mi: 0, p: 1 }], manual: false, ...over }
}

function draft(over: Partial<Segment> = {}): DraftState {
  return { mats: [], segs: [seg(over)], infos: [] } as never
}

const blocks: PositionedBlock[] = [
  { page: 1, type: 'p', text: '甲', rect: { x: 0, y: 0, w: 1, h: 1, approx: false, precision: 'exact' } },
  { page: 1, type: 'p', text: '乙', rect: { x: 0, y: 1, w: 1, h: 1, approx: false, precision: 'exact' } },
]

describe('setSegmentMarkdown', () => {
  it('覆盖正文', () => {
    const d = setSegmentMarkdown(draft({ md: '旧正文' }), 0, '新正文')
    expect(d.segs[0]!.md).toBe('新正文')
  })

  it('内容没变时返回原对象（不往 Undo 栈塞空改动）', () => {
    const before = draft({ md: '正文' })
    expect(setSegmentMarkdown(before, 0, '正文')).toBe(before)
  })

  it('去掉尾部空白后再比较，避免末尾换行算一次改动', () => {
    const before = draft({ md: '正文' })
    expect(setSegmentMarkdown(before, 0, '正文\n\n')).toBe(before)
  })

  it('清空正文后 md 置为 undefined（而不是空串）', () => {
    const d = setSegmentMarkdown(draft({ md: '正文' }), 0, '   ')
    expect(d.segs[0]!.md).toBeUndefined()
  })

  it('不动定位块', () => {
    const d = setSegmentMarkdown(draft({ md: '正文', blocks }), 0, '新正文')
    expect(d.segs[0]!.blocks).toEqual(blocks)
  })

  it('下标越界时原样返回', () => {
    const before = draft({ md: '正文' })
    expect(setSegmentMarkdown(before, 9, 'x')).toBe(before)
  })
})

describe('removeSegmentBlock', () => {
  it('按 key 精确删掉一个块', () => {
    const d = draft({ md: '正文', blocks })
    const key = blockKeyOf(d.segs[0]!, blocks[0]!, 0)
    const out = removeSegmentBlock(d, 0, key)

    expect(out.segs[0]!.blocks).toHaveLength(1)
    expect(out.segs[0]!.blocks![0]!.text).toBe('乙')
  })

  it('删框不影响正文', () => {
    const d = draft({ md: '正文', blocks })
    const out = removeSegmentBlock(d, 0, blockKeyOf(d.segs[0]!, blocks[1]!, 1))
    expect(out.segs[0]!.md).toBe('正文')
  })

  it('删掉最后一个块后 blocks 置 undefined（而不是空数组）', () => {
    let d = draft({ blocks })
    d = removeSegmentBlock(d, 0, blockKeyOf(d.segs[0]!, blocks[0]!, 0))
    d = removeSegmentBlock(d, 0, blockKeyOf(d.segs[0]!, blocks[1]!, 1))
    expect(d.segs[0]!.blocks).toBeUndefined()
  })

  it('key 对不上时返回原对象', () => {
    const before = draft({ blocks })
    expect(removeSegmentBlock(before, 0, 's1:99:0')).toBe(before)
  })

  it('没有块的段不抛', () => {
    const before = draft()
    expect(removeSegmentBlock(before, 0, 's1:1:0')).toBe(before)
  })
})

describe('setSegmentBlockText（改一行，同步进正文）', () => {
  const md = '一、申报主体\n债权人：甲\n债务人：乙'

  it('改块文字的同时把 md 里对应的那段原文换掉', () => {
    const d = draft({ md, blocks })
    const key = blockKeyOf(d.segs[0]!, blocks[0]!, 0)
    const out = setSegmentBlockText(d, 0, key, '债权人：甲某')

    expect(out.segs[0]!.blocks![0]!.text).toBe('债权人：甲某')
    // md 里「甲」被替换 —— 只改块不改 md 会让「列表改好了、正文还是错的」
    expect(out.segs[0]!.md).toContain('债权人：甲某')
    expect(out.segs[0]!.md).not.toMatch(/债权人为?甲(?!某)/)
  })

  it('md 里找不到该块原文时，只改块、不动正文（不乱替换别处的字）', () => {
    const d = draft({ md: '完全无关的正文', blocks })
    const key = blockKeyOf(d.segs[0]!, blocks[0]!, 0)
    const out = setSegmentBlockText(d, 0, key, '新文字')

    expect(out.segs[0]!.blocks![0]!.text).toBe('新文字')
    expect(out.segs[0]!.md).toBe('完全无关的正文')
  })

  it('只改目标那一块，其余块不受影响', () => {
    const d = draft({ md, blocks })
    const key = blockKeyOf(d.segs[0]!, blocks[1]!, 1)
    const out = setSegmentBlockText(d, 0, key, '债务人：乙某')

    expect(out.segs[0]!.blocks![0]!.text).toBe('甲')
    expect(out.segs[0]!.blocks![1]!.text).toBe('债务人：乙某')
  })

  it('key 对不上时返回原对象', () => {
    const before = draft({ md, blocks })
    expect(setSegmentBlockText(before, 0, 's1:99:0', 'x')).toBe(before)
  })
})

/**
 * P0-4：块级编辑必须打 manualEdit 痕迹（否则重跑识别静默抹掉律师逐块核对的成果），
 * 且同步进 md 时要按**页锚点 + 同页同文序号**定位，不是全段首次匹配。
 */
describe('setSegmentBlockText：人工痕迹与精确锚点', () => {
  const stamp = '已核对与原件相符'
  const md = `# 核验\n\n${stamp}\n正文一\n\n第二页\n${stamp}`
  const pageSpans = [
    { page: 1, start: md.indexOf(stamp), end: md.indexOf('\n\n第二页') },
    { page: 2, start: md.indexOf('第二页'), end: md.length },
  ]
  const twoPageBlocks: PositionedBlock[] = [
    { page: 1, type: 'text', text: stamp, rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' } },
    { page: 1, type: 'text', text: '正文一', rect: { x: 0, y: 0.2, w: 1, h: 0.1, approx: false, precision: 'exact' } },
    { page: 2, type: 'text', text: stamp, rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' } },
  ]

  function pdfDraft(over: Partial<Segment> = {}): DraftState {
    return {
      mats: [{ partIndex: 0, n: '证据.pdf', k: 'pdf', pages: 2 }],
      segs: [{
        id: 's1', t: '', fn: '证据.pdf', refs: [{ mi: 0, p: 1 }, { mi: 0, p: 2 }], manual: false,
        md, pageSpans, blocks: twoPageBlocks, ...over,
      }],
      infos: [],
    }
  }

  const suggestions = [{
    page_start: 1, page_end: 2, segment_type: 'other', segment_label: '未识别材料',
    filename: '证据.pdf', confidence: 0.9, review_flag: '', content_md: '重跑后的新正文',
  }] as PdfSplitSegmentSuggestion[]

  it('改块即打 manualEdit.md：重跑前的冲突询问能看见它（不再静默覆盖）', () => {
    const d = pdfDraft()
    const out = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[1]!, 1), '正文一（已核对）')
    expect(out.segs[0]!.manualEdit).toMatchObject({ md: true })
    expect(out.segs[0]!.manualEdit?.at).toEqual(expect.any(String))
    const conflict = detectAutoSplitConflicts(out, 0, suggestions)
    expect(conflict?.edited[0]?.what).toContain('md')
    // 修前：块改了但没打痕迹 → 冲突询问返回 null → 律师的核对被重跑抹掉
    expect(detectAutoSplitConflicts(d, 0, suggestions)).toBeNull()
  })

  it('跨页同文只改本页那一处（第一页的核验语原样保留）', () => {
    const d = pdfDraft()
    const out = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[2]!, 2), '第二页已核对')
    expect(out.segs[0]!.md!.indexOf(stamp)).toBe(md.indexOf(stamp))
    expect(out.segs[0]!.md!.endsWith('第二页已核对')).toBe(true)
    expect(out.segs[0]!.md!.match(new RegExp(stamp, 'g'))).toHaveLength(1)
  })

  it('同页重复文字按块序改第 n 处，不是首次匹配', () => {
    const repeated = `# 核验\n\n${stamp}\n正文一\n${stamp}`
    const spans = [{ page: 1, start: repeated.indexOf(stamp), end: repeated.length }]
    const blks: PositionedBlock[] = [
      { ...twoPageBlocks[0]!, text: stamp },
      { ...twoPageBlocks[1]!, text: stamp },
    ]
    const d = pdfDraft({ md: repeated, pageSpans: spans, blocks: blks, refs: [{ mi: 0, p: 1 }] })
    const out = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, blks[1]!, 1), '第二处已改')
    expect(out.segs[0]!.md).toBe(`# 核验\n\n${stamp}\n正文一\n第二处已改`)
  })

  it('锚不到原文：md 留旧值但打 mdDrift（不静默漂移），痕迹照样打', () => {
    const d = pdfDraft({ md: '与块完全无关的正文', pageSpans: undefined, blocks: twoPageBlocks })
    const out = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[0]!, 0), '新文字')
    expect(out.segs[0]!.md).toBe('与块完全无关的正文')
    expect(out.segs[0]!.blocks![0]!.text).toBe('新文字')
    expect(out.segs[0]!.mdDrift).toBe(true)
    expect(out.segs[0]!.manualEdit).toMatchObject({ md: true })
  })

  it('同步成功不打 mdDrift；整段改写后清掉痕迹与失效的页锚点', () => {
    const d = pdfDraft()
    const ok = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[1]!, 1), '正文一（已核对）')
    expect(ok.segs[0]!.mdDrift).toBeUndefined()
    const drifted = setSegmentBlockText(pdfDraft({ md: '无关正文', pageSpans: undefined }), 0, blockKeyOf(d.segs[0]!, twoPageBlocks[0]!, 0), 'x')
    expect(drifted.segs[0]!.mdDrift).toBe(true)
    const rewritten = setSegmentMarkdown(drifted, 0, '律师整段重写的正文')
    expect(rewritten.segs[0]!.mdDrift).toBeUndefined()
    // 整段改写后旧偏移必然失效，留着会让后续块编辑圈错区间
    expect(rewritten.segs[0]!.pageSpans).toBeUndefined()
  })

  it('改完一处后页锚点跟着平移：接着改另一页仍定位正确', () => {
    const d = pdfDraft()
    const first = setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[1]!, 1), '正文一（补了很长一段说明文字）')
    const second = setSegmentBlockText(first, 0, blockKeyOf(first.segs[0]!, twoPageBlocks[2]!, 2), '第二页已核对')
    expect(second.segs[0]!.md).toBe(`# 核验\n\n${stamp}\n正文一（补了很长一段说明文字）\n\n第二页\n第二页已核对`)
    expect(second.segs[0]!.mdDrift).toBeUndefined()
  })

  it('文字没变时返回原引用（不往 Undo 栈塞空改动）', () => {
    const d = pdfDraft()
    expect(setSegmentBlockText(d, 0, blockKeyOf(d.segs[0]!, twoPageBlocks[0]!, 0), stamp)).toBe(d)
  })
})
