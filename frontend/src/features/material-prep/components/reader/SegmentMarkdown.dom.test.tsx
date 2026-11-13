// @vitest-environment jsdom
/**
 * 右侧栏「Markdown 正文」面板单测。
 *
 * 回归背景：`seg.md` 一直在产出，但**没有任何 UI 渲染它**——只被识别当事人
 * 和推断文本在后台消费。律师看不到机器读出了什么，整条识别链路是黑盒。
 *
 * 这里锁三件事：
 * 1. 有 md 就能看到正文；没有 md 给明确说明而不是空白；
 * 2. **双击**才定位（单击只选中文字，不该跳转）；
 * 3. 定位块的 key 与 PageCell 的 hits[].key 同一套，否则高亮对不上。
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

function base(props: Partial<Parameters<typeof SegmentMarkdown>[0]> = {}) {
  return {
    seg: seg({ md: '# 证据目录\n\n原告提交了转账凭证。', blocks }),
    open: true,
    onToggleOpen: vi.fn(),
    focusedBlockKey: null,
    onLocateBlock: vi.fn(),
    ...props,
  }
}

describe('SegmentMarkdown', () => {
  it('展开时每一行就是正文，不再额外渲染一份完整 <pre>', () => {
    const { container, getByText } = render(<SegmentMarkdown {...base()} />)
    // 列表即正文：文字出现在行内
    expect(getByText('原告提交了转账凭证。')).toBeTruthy()
    expect(getByText('被告对此不予认可。')).toBeTruthy()
    // 有定位块时不再有重复的整段渲染
    expect(container.querySelector('pre')).toBeNull()
  })

  it('折叠时不渲染正文，点标题回调切换', () => {
    const onToggleOpen = vi.fn()
    const { container, getByText } = render(<SegmentMarkdown {...base({ open: false, onToggleOpen })} />)
    expect(container.querySelector('pre')).toBeNull()
    fireEvent.click(getByText('Markdown 正文'))
    expect(onToggleOpen).toHaveBeenCalled()
  })

  it('没有 md 时给出明确说明，不渲染空白面板', () => {
    const { container } = render(<SegmentMarkdown {...base({ seg: seg() })} />)
    expect(container.textContent).toContain('该段没有 Markdown 正文')
    expect(container.querySelector('pre')).toBeNull()
  })

  it('人工拆分的段不显示任何正文提示（避免噪声）', () => {
    const { container } = render(<SegmentMarkdown {...base({ seg: seg({ manual: true }) })} />)
    expect(container.textContent).toBe('')
  })

  it('seg 为 null 时整块不渲染（右栏其余部分不受影响）', () => {
    const { container } = render(<SegmentMarkdown {...base({ seg: null })} />)
    expect(container.textContent).toBe('')
  })

  it('单击不触发定位，双击才定位', () => {
    const onLocate = vi.fn()
    const { getByText } = render(<SegmentMarkdown {...base({ onLocateBlock: onLocate })} />)
    const row = getByText('原告提交了转账凭证。')

    fireEvent.click(row)
    expect(onLocate).not.toHaveBeenCalled()

    fireEvent.doubleClick(row)
    expect(onLocate).toHaveBeenCalledWith('s1:1:0')
  })

  it('已定位的块再双击一次 → 传 null（取消）', () => {
    const onLocate = vi.fn()
    const { getByText } = render(
      <SegmentMarkdown {...base({ focusedBlockKey: 's1:1:0', onLocateBlock: onLocate })} />,
    )
    fireEvent.doubleClick(getByText('原告提交了转账凭证。'))
    expect(onLocate).toHaveBeenCalledWith(null)
  })

  it('有定位时给出「取消定位」入口', () => {
    const onLocate = vi.fn()
    const { getByText } = render(
      <SegmentMarkdown {...base({ focusedBlockKey: 's1:1:0', onLocateBlock: onLocate })} />,
    )
    fireEvent.click(getByText('取消定位'))
    expect(onLocate).toHaveBeenCalledWith(null)
  })
})

describe('识别错了怎么办', () => {
  it('右键某一行 → 就地变成输入框，回车保存并回调 (key, 新文字)', () => {
    const onEditBlock = vi.fn()
    const { getByText, container } = render(<SegmentMarkdown {...base({ onEditBlock })} />)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    const ta = container.querySelector('textarea')
    expect(ta).toBeTruthy()

    fireEvent.change(ta!, { target: { value: '我改过的这一行' } })
    fireEvent.keyDown(ta!, { key: 'Enter' })
    expect(onEditBlock).toHaveBeenCalledWith('s1:1:0', '我改过的这一行')
  })

  it('编辑态按 Esc 取消，不回调', () => {
    const onEditBlock = vi.fn()
    const { getByText, container } = render(<SegmentMarkdown {...base({ onEditBlock })} />)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '改了但不保存' } })
    fireEvent.keyDown(container.querySelector('textarea')!, { key: 'Escape' })

    expect(onEditBlock).not.toHaveBeenCalled()
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('删掉画错的定位框，只删框不动正文', () => {
    const onRemoveBlock = vi.fn()
    const { getAllByLabelText } = render(<SegmentMarkdown {...base({ onRemoveBlock })} />)

    fireEvent.click(getAllByLabelText('删除这个定位框')[0]!)
    expect(onRemoveBlock).toHaveBeenCalledWith('s1:1:0')
  })

  it('未提供回调时不渲染删框入口，右键也不进编辑（只读场景）', () => {
    const { queryAllByLabelText, getByText, container } = render(<SegmentMarkdown {...base()} />)
    expect(queryAllByLabelText('删除这个定位框')).toHaveLength(0)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    expect(container.querySelector('textarea')).toBeNull()
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
