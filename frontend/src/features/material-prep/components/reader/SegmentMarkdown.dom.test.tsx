// @vitest-environment jsdom
/**
 * 分段 Markdown 面板单测。
 *
 * 回归背景：`seg.md` 一直在产出，但**没有任何 UI 渲染它**——只被识别当事人
 * 和推断文本在后台消费。律师看不到机器读出了什么，整条识别链路是黑盒。
 *
 * 这里锁两件事：
 * 1. 有 md 就能展开看到正文；没有 md 给明确说明而不是空白；
 * 2. 定位块能点，且点出来的 key 与 PageCell 的 hits[].key 同一套（否则高亮对不上）。
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { blockKeyOf } from '../../draft/block-keys'
import { SegmentMarkdown } from './SegmentMarkdown'
import type { PositionedBlock, Segment } from '../../types'

function seg(over: Partial<Segment> = {}): Segment {
  return {
    id: 's1',
    t: '证据',
    fn: '证据一',
    refs: [{ mi: 0, p: 1 }],
    manual: false,
    ...over,
  }
}

const blocks: PositionedBlock[] = [
  { page: 1, type: 'paragraph', text: '原告提交了转账凭证。', rect: { x: 0.1, y: 0.2, w: 0.5, h: 0.05, approx: false } },
  { page: 1, type: 'paragraph', text: '被告对此不予认可。', rect: { x: 0.1, y: 0.4, w: 0.5, h: 0.05, approx: false } },
]

describe('SegmentMarkdown', () => {
  it('有 md 时默认折叠，展开后能看到正文', () => {
    const { container, getByText } = render(
      <SegmentMarkdown seg={seg({ md: '# 证据目录\n\n原告提交了转账凭证。' })} focusedBlockKey={null} onFocusBlock={() => {}} />,
    )

    // 折叠态不渲染 <pre>
    expect(container.querySelector('pre')).toBeNull()

    fireEvent.click(getByText('Markdown 正文'))
    expect(container.querySelector('pre')?.textContent).toContain('原告提交了转账凭证。')
  })

  it('没有 md 时给出明确说明，不渲染空白面板', () => {
    const { container } = render(<SegmentMarkdown seg={seg()} focusedBlockKey={null} onFocusBlock={() => {}} />)

    expect(container.textContent).toContain('该段没有 Markdown 正文')
    expect(container.querySelector('pre')).toBeNull()
  })

  it('人工拆分的段不显示任何正文提示（避免噪声）', () => {
    const { container } = render(
      <SegmentMarkdown seg={seg({ manual: true })} focusedBlockKey={null} onFocusBlock={() => {}} />,
    )
    expect(container.textContent).toBe('')
  })

  it('点定位块回调其 key', () => {
    const onFocus = vi.fn()
    const s = seg({ md: '正文', blocks })
    const { getByText } = render(<SegmentMarkdown seg={s} focusedBlockKey={null} onFocusBlock={onFocus} />)

    fireEvent.click(getByText('Markdown 正文'))
    fireEvent.click(getByText('原告提交了转账凭证。'))
    expect(onFocus).toHaveBeenCalledWith('s1:1:0')
  })

  it('已高亮的块再点一次 → 传 null（取消高亮）', () => {
    const onFocus = vi.fn()
    const s = seg({ md: '正文', blocks })
    const { getByText } = render(
      <SegmentMarkdown seg={s} focusedBlockKey="s1:1:0" onFocusBlock={onFocus} />,
    )

    fireEvent.click(getByText('Markdown 正文'))
    fireEvent.click(getByText('原告提交了转账凭证。'))
    expect(onFocus).toHaveBeenCalledWith(null)
  })
})

describe('blockKeyOf', () => {
  it('与 Flow.hitsByPage 的 key 规则一致：段 id + 绝对页号 + 同页内序号', () => {
    expect(blockKeyOf(seg({ blocks }), blocks[0]!, 0)).toBe('s1:1:0')
    expect(blockKeyOf(seg({ blocks }), blocks[1]!, 1)).toBe('s1:1:1')
  })

  it('跨页时每页序号从 0 重新开始', () => {
    const multi: PositionedBlock[] = [
      { page: 1, type: 'p', text: 'a', rect: { x: 0, y: 0, w: 1, h: 1, approx: false } },
      { page: 2, type: 'p', text: 'b', rect: { x: 0, y: 0, w: 1, h: 1, approx: false } },
      { page: 2, type: 'p', text: 'c', rect: { x: 0, y: 0, w: 1, h: 1, approx: false } },
    ]
    const s = seg({ blocks: multi })
    expect(blockKeyOf(s, multi[0]!, 0)).toBe('s1:1:0')
    expect(blockKeyOf(s, multi[1]!, 1)).toBe('s1:2:0')
    expect(blockKeyOf(s, multi[2]!, 2)).toBe('s1:2:1')
  })
})
