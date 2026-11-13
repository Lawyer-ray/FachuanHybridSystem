/**
 * 「识别错了怎么办」的两个纯函数：改正文、删错框。
 *
 * 这两件事必须分开：框画歪 ≠ 文字读错。删框不能把正文一起弄没了，
 * 改正文也不该顺手把定位块清空。
 */
import { describe, expect, it } from 'vitest'

import { blockKeyOf } from './block-keys'
import { removeSegmentBlock, setSegmentBlockText, setSegmentMarkdown } from './segments'
import type { DraftState, PositionedBlock, Segment } from '../types'

function seg(over: Partial<Segment> = {}): Segment {
  return { id: 's1', t: '', fn: '证据一', refs: [{ mi: 0, p: 1 }], manual: false, ...over }
}

function draft(over: Partial<Segment> = {}): DraftState {
  return { mats: [], segs: [seg(over)], infos: [] } as never
}

const blocks: PositionedBlock[] = [
  { page: 1, type: 'p', text: '甲', rect: { x: 0, y: 0, w: 1, h: 1, approx: false } },
  { page: 1, type: 'p', text: '乙', rect: { x: 0, y: 1, w: 1, h: 1, approx: false } },
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
