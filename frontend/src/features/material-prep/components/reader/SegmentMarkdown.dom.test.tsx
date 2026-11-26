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
import type { EngineDisagreement, PositionedBlock, Segment } from '../../types'

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
  { page: 1, type: 'paragraph', text: '原告提交了转账凭证。', rect: { x: 0.1, y: 0.2, w: 0.5, h: 0.05, approx: false, precision: 'exact' } },
  { page: 1, type: 'paragraph', text: '被告对此不予认可。', rect: { x: 0.1, y: 0.4, w: 0.5, h: 0.05, approx: false, precision: 'exact' } },
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

  /**
   * 用户反馈（原话）：「需要复核的材料，为什么没有把复核的问题展示在右边对应
   * Markdown 处——那我怎么知道什么要复核」。中栏段头只有一个「建议复核」徽标，
   * 右栏正文一个字不提，等于让律师自己猜该核对什么。
   */
  it('低置信度的段：正文面板顶部写出「为什么复核」和「核对什么」', () => {
    const { container } = render(
      <SegmentMarkdown
        {...base({
          seg: seg({
            md: '# 证据目录\n\n原告提交了转账凭证。',
            reviewFlag: 'low_confidence',
            sourceMethod: 'layout_title',
            confidence: 0.62,
          }),
        })}
      />,
    )
    const hint = container.querySelector('[data-review-hint]') as HTMLElement
    expect(hint).toBeTruthy()
    expect(hint.textContent).toContain('建议复核')
    // 原因（不是只有「建议复核」四个字）
    expect(hint.textContent).toContain('起点是按版面标题推断的')
    // 62% 不低，就别拿它当理由（真实反馈：「置信度 90% 你还要我复核？」）
    expect(hint.textContent).not.toContain('自动分段置信度')
    // 行动指引
    expect(hint.textContent).toContain('请核对本段起止页与材料名')
  })

  /**
   * 置信度 90% 仍被要求复核时，必须说清「复核的是边界，不是文字」——
   * 后端触发它的是边界二审没结论这类结构信号（刻意不降模型自报的置信度）。
   */
  it('高置信度仍要复核时：写明要核对的是分段边界', () => {
    const { container } = render(
      <SegmentMarkdown
        {...base({
          seg: seg({ md: '# 证据目录', reviewFlag: 'low_confidence', sourceMethod: 'llm', confidence: 0.9 }),
        })}
      />,
    )
    const hint = container.querySelector('[data-review-hint]') as HTMLElement
    expect(hint.textContent).toContain('文字识别置信度 90%')
    expect(hint.textContent).toContain('要核对的是分段边界')
  })

  it('不需要复核的段不出现复核提示条', () => {
    const { container } = render(<SegmentMarkdown {...base()} />)
    expect(container.querySelector('[data-review-hint]')).toBeNull()
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

  it('编辑态有显式的「保存 / 取消」按钮', () => {
    const onEditBlock = vi.fn()
    const { getByText, container } = render(<SegmentMarkdown {...base({ onEditBlock })} />)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    expect(getByText('保存')).toBeTruthy()
    expect(getByText('取消')).toBeTruthy()

    fireEvent.change(container.querySelector('textarea')!, { target: { value: '改好的行' } })
    fireEvent.click(getByText('保存'))
    expect(onEditBlock).toHaveBeenCalledWith('s1:1:0', '改好的行')
  })

  it('点「取消」放弃改动，必须不写回', () => {
    const onEditBlock = vi.fn()
    const { getByText, container } = render(<SegmentMarkdown {...base({ onEditBlock })} />)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '不要保存我' } })
    fireEvent.click(getByText('取消'))

    expect(onEditBlock).not.toHaveBeenCalled()
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('失焦不自动保存（法律正文不能「切走就提交」）', () => {
    const onEditBlock = vi.fn()
    const { getByText, container } = render(<SegmentMarkdown {...base({ onEditBlock })} />)

    fireEvent.contextMenu(getByText('原告提交了转账凭证。'))
    const ta = container.querySelector('textarea')!
    fireEvent.change(ta, { target: { value: '只是切走了不该保存' } })
    fireEvent.blur(ta)

    expect(onEditBlock).not.toHaveBeenCalled()
    // 仍停在编辑态，等用户明确选择
    expect(container.querySelector('textarea')).toBeTruthy()
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
      { page: 1, type: 'p', text: 'a', rect: { x: 0, y: 0, w: 1, h: 1, approx: false, precision: 'exact' } },
      { page: 2, type: 'p', text: 'b', rect: { x: 0, y: 0, w: 1, h: 1, approx: false, precision: 'exact' } },
      { page: 2, type: 'p', text: 'c', rect: { x: 0, y: 0, w: 1, h: 1, approx: false, precision: 'exact' } },
    ]
    const s = seg({ blocks: multi })
    expect(blockKeyOf(s, multi[0]!, 0)).toBe('s1:1:0')
    expect(blockKeyOf(s, multi[1]!, 1)).toBe('s1:2:0')
    expect(blockKeyOf(s, multi[2]!, 2)).toBe('s1:2:1')
  })
})

/**
 * 可疑点清单。
 *
 * 背景：`findSuspects` 给的是 **markdown 行号**，而面板渲染的是 `blocks`，两者没有
 * 对应关系（`seg.md` 是后端把标题 + 各页块用空行拼起来的，一个表格块在 md 里展开成
 * 几十行）。所以这里**不在行内画点**，而是在正文下方给一份清单：每条带命中原文与
 * 「查看原页」。这组用例锁的就是「清单手法」——指错行比不指更糟。
 */
describe('可疑点清单', () => {
  /** 一段流水正文：D3.00 会被判成金额前缀（high） */
  const riskyMd = [
    '# 银行流水',
    '',
    '| 交易日期 | 摘要 | 发生额 |',
    '| --- | --- | --- |',
    '| 20170301 | 手续费 | D3.00 |',
  ].join('\n')

  it('没有可疑点时不渲染清单', () => {
    const { container } = render(<SegmentMarkdown {...base()} />)
    expect(container.textContent).not.toContain('可疑')
  })

  it('有可疑点时给段头汇总（总数 + 高危数），并把命中原文与提示列出来', () => {
    const onLocate = vi.fn()
    const { container, getByText } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: riskyMd, blocks }), onLocateBlock: onLocate })} />,
    )

    expect(getByText(/本段有 \d+ 处可疑/)).toBeTruthy()
    // 命中原文直接展示：律师一眼就知道是哪个数
    expect(getByText('D3.00')).toBeTruthy()
    // 提示文案来自 md-suspects（D/C 前缀那条）
    expect(container.textContent).toContain('借贷标记')
  })

  it('「查看原页」用文本匹配定位到包含该片段的块，匹配不到就不给按钮', () => {
    const onLocate = vi.fn()
    // 让 D3.00 真的出现在某个 block 的 text 里 → 应该能定位
    const withHit: PositionedBlock[] = [
      { page: 2, type: 'table', text: '手续费 D3.00', rect: { x: 0, y: 0, w: 1, h: 1, approx: false, precision: 'exact' } },
    ]
    const { getByText } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: riskyMd, blocks: withHit }), onLocateBlock: onLocate })} />,
    )
    fireEvent.click(getByText('查看原页'))
    expect(onLocate).toHaveBeenCalledWith('s1:2:0')
  })

  it('命中片段不在任何块里时不显示「查看原页」（不做假跳转）', () => {
    // 默认 blocks 里没有 D3.00
    const { queryByText } = render(<SegmentMarkdown {...base({ seg: seg({ md: riskyMd, blocks }) })} />)
    expect(queryByText('查看原页')).toBeNull()
  })

  it('超过 5 条默认折叠，点标题展开，再点收起', () => {
    const rows = Array.from({ length: 8 }, (_, i) => `| 2017030${i + 1} | 代付款 | D${i + 1}.00 |`)
    const many = [
      '# 流水',
      '',
      '| 交易日期 | 摘要 | 发生额 |',
      '| --- | --- | --- |',
      ...rows,
    ].join('\n')

    const { getByText, queryByText, queryAllByText } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: many, blocks }) })} />,
    )

    // 折叠态：只有标题，没有单条
    expect(getByText(/8 处可疑/)).toBeTruthy()
    expect(queryByText('展开')).toBeTruthy()
    expect(queryAllByText(/借贷标记/)).toHaveLength(0)

    fireEvent.click(getByText(/8 处可疑/))
    expect(queryAllByText(/借贷标记/)).toHaveLength(8)

    fireEvent.click(getByText(/8 处可疑/))
    expect(queryAllByText(/借贷标记/)).toHaveLength(0)
  })
})

/**
 * 页面框双击 → Markdown 对应那条进入修改态。
 *
 * 律师的直觉是「我在原件上看到这行不对，点它就该能就地改」。
 * 这里锁住：请求到达即进编辑、消费后即清空（否则同块再高亮会反复弹输入框）。
 */
describe('页面框双击 → 进入修改', () => {
  it('editRequestKey 指向某块时，该行直接进入编辑态', () => {
    const onEditBlock = vi.fn()
    const onEditRequestHandled = vi.fn()
    const { container } = render(
      <SegmentMarkdown
        {...base({ onEditBlock, editRequestKey: 's1:1:0', onEditRequestHandled })}
      />,
    )
    // 该行渲染成 textarea（编辑态）
    expect(container.querySelector('textarea')).toBeTruthy()
    // 一次性语义：消费后必须清空请求
    expect(onEditRequestHandled).toHaveBeenCalled()
  })

  it('没有逐块编辑能力（无 blocks）时退回整段编辑', () => {
    const onEditMarkdown = vi.fn()
    const onEditRequestHandled = vi.fn()
    // 无定位块的段（本地 OCR / 旧任务）：只能整段改
    const b = base()
    const noBlocks = {
      ...b,
      seg: { ...b.seg!, blocks: undefined },
      editRequestKey: 's1:1:0',
      onEditRequestHandled,
      onEditMarkdown,
      onEditBlock: undefined,
    }
    const { container } = render(<SegmentMarkdown {...noBlocks} />)
    expect(container.querySelector('textarea')).toBeTruthy()
    expect(onEditRequestHandled).toHaveBeenCalled()
  })
})

/**
 * 「两个引擎都不对」→ 点「修改」：编辑态要用那侧引擎全文作起点。
 *
 * 这里锁的是**预填本身**：以前草稿留在 BlockRow 里用 effect 灌种子文本，
 * 输入框会先渲染一轮本行原文再被改掉；现在编辑态是自带 useState 初值的子组件，
 * 首帧就是种子文本。
 */
describe('种子文本预填（点「修改」用引擎全文作起点）', () => {
  const SEED_A = '引擎 B 读作：原告提交了转账凭据。'
  const SEED_B = '引擎 A 读作：原告提交了转账凭证一张。'

  it('进入编辑态首帧就是种子文本，不是本行原文', () => {
    const { container } = render(
      <SegmentMarkdown
        {...base({ onEditBlock: vi.fn(), editRequestKey: 's1:1:0', editRequestSeed: SEED_A })}
      />,
    )
    const ta = container.querySelector('textarea') as HTMLTextAreaElement
    expect(ta.value).toBe(SEED_A)
  })

  it('同一种子文本下父级重渲染不冲掉律师已打的字', () => {
    const props = base({ onEditBlock: vi.fn(), editRequestKey: 's1:1:0', editRequestSeed: SEED_A })
    const { container, rerender } = render(<SegmentMarkdown {...props} />)
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '我改到一半' } })

    rerender(<SegmentMarkdown {...props} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe('我改到一半')
  })

  it('换成另一侧的种子文本时，输入框重新预填', () => {
    const props = base({ onEditBlock: vi.fn(), editRequestKey: 's1:1:0', editRequestSeed: SEED_A })
    const { container, rerender } = render(<SegmentMarkdown {...props} />)
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '第一版的改法' } })

    rerender(<SegmentMarkdown {...props} editRequestSeed={SEED_B} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe(SEED_B)
  })
})

/**
 * 质量提示条：正文里只有几行零散字符时，律师**看不出那是图纸**。
 * 提示条必须写在标题下方（开始读正文之前），并且能一步跳回原页。
 */
describe('质量提示条（图纸 / 稀疏页）', () => {
  it('覆盖图形页时逐页提示（每页一行，写明是哪一页）', () => {
    const { container } = render(<SegmentMarkdown {...base({ graphicPages: [147, 148] })} />)
    const hints = container.querySelectorAll('[data-quality-hint]')
    expect(hints).toHaveLength(2)
    expect(hints[0]!.textContent).toContain('P147 疑似图纸')
    expect(hints[0]!.textContent).toContain('正文可能不完整')
    expect(hints[0]!.textContent).toContain('建议核对原页')
    expect(hints[1]!.textContent).toContain('P148')
  })

  /**
   * 落点：**挂在该页正文第一行之前**，而不是栏顶一张清单。
   * 同一段里双引擎分歧已经这么做（读到 P2 就看到 P2 的分歧），质量问题照同一套走，
   * 否则律师得在栏顶记页号、再回正文里找「P2 在哪」。
   */
  it('提示挂在该页正文第一行之前', () => {
    const twoPages = seg({
      md: '# 证据目录\n\n一\n\n二',
      refs: [
        { mi: 0, p: 1 },
        { mi: 0, p: 2 },
      ],
      blocks: [
        ...blocks,
        {
          page: 2,
          type: 'paragraph',
          text: '第二页正文。',
          rect: { x: 0.1, y: 0.2, w: 0.5, h: 0.05, approx: false, precision: 'exact' },
        },
      ],
    })
    const { container, getByText } = render(<SegmentMarkdown {...base({ seg: twoPages, graphicPages: [2] })} />)
    const hint = container.querySelector('[data-quality-hint]') as HTMLElement
    const lastOfP1 = getByText('被告对此不予认可。')
    const firstOfP2 = getByText('第二页正文。')
    // 在第一页正文之后、第二页正文之前
    expect(lastOfP1.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(hint.compareDocumentPosition(firstOfP2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  /** 图纸页往往一个字都没取出来（没有正文行可挂）：提示必须自己成一行，否则等于没提示 */
  it('提示页没有正文行时，提示仍然出现（补在正文之后）', () => {
    const { container } = render(<SegmentMarkdown {...base({ graphicPages: [147] })} />)
    expect(container.querySelector('[data-quality-hint]')).toBeTruthy()
  })

  it('提示条在标题之下、正文之上', () => {
    const { container, getByText } = render(<SegmentMarkdown {...base({ graphicPages: [147] })} />)
    const hint = container.querySelector('[data-quality-hint]') as HTMLElement
    const title = getByText('Markdown 正文')
    // DOCUMENT_POSITION_FOLLOWING：hint 出现在标题之后
    expect(title.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('点提示条跳到第一个图形页', () => {
    const onGotoPage = vi.fn()
    const { container } = render(<SegmentMarkdown {...base({ graphicPages: [147, 148], onGotoPage })} />)
    fireEvent.click(container.querySelector('[data-quality-hint]')!)
    expect(onGotoPage).toHaveBeenCalledWith(147)
  })

  it('没有 onGotoPage 时提示条只陈述、不可点', () => {
    const { container } = render(<SegmentMarkdown {...base({ graphicPages: [147] })} />)
    const hint = container.querySelector('[data-quality-hint]') as HTMLElement
    expect(hint.tagName).not.toBe('BUTTON')
  })

  it('段带 quality_flags 但无图形页时，按标记文字提示', () => {
    const { container } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: '几行字', qualityFlags: ['sparse'] }) })} />,
    )
    const hint = container.querySelector('[data-quality-hint]') as HTMLElement
    expect(hint.textContent).toContain('文字稀疏')
  })

  it('旧任务没有质量数据时不渲染提示条', () => {
    const { container } = render(<SegmentMarkdown {...base()} />)
    expect(container.querySelector('[data-quality-hint]')).toBeNull()
  })
})

/**
 * 证件页提示：「这页是图纸」与「这页是身份证但姓名没读出」不能共用一句话。
 * 前者是这页本来就没字，后者是该抄进卷宗的字段丢了——混在一起会让人以为
 * 证件页也跟图纸一样不用管。
 */
describe('质量提示条（证件页）', () => {
  const idCard = { page: 23, doc: 'id_card', missing: ['姓名', '身份证号', '住址'] }

  it('证件页单独成行，逐页说清类型与缺的字段', () => {
    const { container } = render(<SegmentMarkdown {...base({ docPages: [idCard] })} />)
    const hint = container.querySelector('[data-doc-hint]') as HTMLElement
    expect(hint).toBeTruthy()
    expect(hint.textContent).toContain('P23 身份证')
    expect(hint.textContent).toContain('缺：姓名 / 身份证号 / 住址')
    expect(hint.textContent).toContain('建议核对原页')
    // 不是「疑似图纸」那套文案
    expect(hint.textContent).not.toContain('疑似图纸')
  })

  it('证件页与图纸页同时存在时各占一行，证件在前', () => {
    const { container } = render(<SegmentMarkdown {...base({ docPages: [idCard], graphicPages: [147] })} />)
    const doc = container.querySelector('[data-doc-hint]') as HTMLElement
    const graphic = container.querySelector('[data-quality-hint]') as HTMLElement
    expect(doc).toBeTruthy()
    expect(graphic).toBeTruthy()
    expect(graphic.textContent).toContain('疑似图纸')
    // 证件页排在图纸页之前：先处理「该抄的字段丢了」
    expect(doc.compareDocumentPosition(graphic) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('点证件提示条跳到那一页（不是第一张图形页）', () => {
    const onGotoPage = vi.fn()
    const { container } = render(
      <SegmentMarkdown {...base({ docPages: [idCard], graphicPages: [147], onGotoPage })} />,
    )
    fireEvent.click(container.querySelector('[data-doc-hint]')!)
    expect(onGotoPage).toHaveBeenCalledWith(23)
  })

  it('多页证件各自一行；说不出缺哪个字段时说「关键字段可能未读出」', () => {
    const { container } = render(
      <SegmentMarkdown
        {...base({
          docPages: [idCard, { page: 42, doc: 'id_card', missing: [] }],
        })}
      />,
    )
    const rows = container.querySelectorAll('[data-doc-hint]')
    expect(rows).toHaveLength(2)
    expect(rows[1]!.textContent).toContain('P42 身份证')
    // 不冒充「缺：」半句话，也不静默省略类型
    expect(rows[1]!.textContent).toContain('关键字段可能未读出')
    expect(rows[1]!.textContent).not.toContain('缺：')
  })

  it('没有 onGotoPage 时证件提示只陈述、不可点', () => {
    const { container } = render(<SegmentMarkdown {...base({ docPages: [idCard] })} />)
    const hint = container.querySelector('[data-doc-hint]') as HTMLElement
    expect(hint.tagName).not.toBe('BUTTON')
  })

  it('旧任务没有 doc_hints 时不渲染任何提示条（含证件行）', () => {
    const { container } = render(<SegmentMarkdown {...base({ docPages: [] })} />)
    expect(container.querySelector('[data-doc-hint]')).toBeNull()
    expect(container.querySelector('[data-quality-hint]')).toBeNull()
  })
})

describe('SegmentMarkdown：分歧按页挂载', () => {
  // 多页段：第 1 页两行、第 3 页一行。分歧应挂在各页**第一行之前**。
  const multiPageBlocks: PositionedBlock[] = [
    { page: 1, type: 'paragraph', text: '第一页第一行。', rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact' } },
    { page: 1, type: 'paragraph', text: '第一页第二行。', rect: { x: 0, y: 0.1, w: 1, h: 0.1, approx: false, precision: 'exact' } },
    { page: 3, type: 'paragraph', text: '第三页第一行。', rect: { x: 0, y: 0.2, w: 1, h: 0.1, approx: false, precision: 'exact' } },
  ]

  function dis(pageNo: number): EngineDisagreement {
    return {
      page_no: pageNo,
      kind: 'char',
      severity: 'high',
      variants: [
        { engine: 'mineru', text: '记 A' },
        { engine: 'paddleocr_vl', text: '记 B' },
      ] as EngineDisagreement['variants'],
      context: 'ctx',
      anchor_hit: false,
      similarity: 0.8,
    }
  }

  function renderWith(items: EngineDisagreement[]) {
    return render(
      <SegmentMarkdown
        {...base({
          seg: seg({ md: 'x', blocks: multiPageBlocks, refs: [{ mi: 0, p: 1 }, { mi: 0, p: 3 }] }),
        })}
        engineItems={items}
        engineKeys={items.map((d) => `${d.page_no}:k`)}
      />,
    )
  }

  it('分歧按页挂到该页第一行之前，而不是全部堆在栏顶', () => {
    const { container } = renderWith([dis(1), dis(3)])
    const inlines = Array.from(container.querySelectorAll('[data-engine-inline]'))
    expect(inlines).toHaveLength(2)
    // 每块的标题带页码，律师能一眼对上正文哪一页
    expect(inlines[0]!.textContent).toContain('P1 分歧')
    expect(inlines[1]!.textContent).toContain('P3 分歧')

    // 顺序断言：P1 分歧 → 第一页第一行 → … → P3 分歧 → 第三页第一行
    const html = container.innerHTML
    expect(html.indexOf('P1 分歧')).toBeLessThan(html.indexOf('第一页第一行'))
    expect(html.indexOf('第一页第二行')).toBeLessThan(html.indexOf('P3 分歧'))
    expect(html.indexOf('P3 分歧')).toBeLessThan(html.indexOf('第三页第一行'))
  })

  it('同一页多行时只在该页首行前插一次，不重复', () => {
    const { container } = renderWith([dis(1)])
    const inlines = Array.from(container.querySelectorAll('[data-engine-inline]'))
    expect(inlines).toHaveLength(1)
  })

  it('只挂本段覆盖页的分歧（段外页号不渲染）', () => {
    const { container } = renderWith([dis(1), dis(99)])
    const inlines = Array.from(container.querySelectorAll('[data-engine-inline]'))
    expect(inlines).toHaveLength(1)
    expect(container.textContent).not.toContain('P99 分歧')
  })

  it('没有分歧时不渲染任何分歧块', () => {
    const { container } = renderWith([])
    expect(container.querySelectorAll('[data-engine-inline]')).toHaveLength(0)
  })
})

/**
 * P3-2：有定位块时也要能看到/改到**原始 Markdown**（现在叫「渲染 / 源码」两档）。
 * 纯文本行看不出表格结构与标题层级，而那正是 OCR 最易错处；逐块改也改不动整段结构。
 */
describe('正文视图切换', () => {
  const tableMd = '# 流水\n\n| 日期 | 金额 |\n| --- | --- |\n| 20260101 | 100 |'

  it('有定位块时默认按块渲染，切到「渲染」才看得到表格结构', () => {
    const { container, getByText } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: tableMd, blocks }) })} />,
    )
    expect(container.querySelector('table')).toBeNull()
    expect(container.querySelector('pre')).toBeNull()
    fireEvent.click(getByText('渲染'))
    expect(container.querySelector('table')).toBeTruthy()
    expect(container.querySelectorAll('td')).toHaveLength(2)
    fireEvent.click(getByText('分块'))
    expect(container.querySelector('table')).toBeNull()
  })

  /**
   * **只有一个视图切换器**。改前是「定位块 / 原始 Markdown」+「渲染 / 源码 / 编辑整段」
   * 两套叠着，切过去之后控件从两个变三个、选中态还换一套样式——侧边栏「乱」的主因。
   */
  it('视图切换只有一套 tab，旧的「原始 Markdown」入口已不存在', () => {
    const { queryByText, getByText } = render(<SegmentMarkdown {...base()} />)
    expect(getByText('分块')).toBeTruthy()
    expect(getByText('渲染')).toBeTruthy()
    expect(getByText('源码')).toBeTruthy()
    expect(queryByText('原始 Markdown')).toBeNull()
    expect(queryByText('定位块')).toBeNull()
  })

  it('源码视图：点「源码」看原文', () => {
    const { container, getByText } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: tableMd, blocks }) })} />,
    )
    fireEvent.click(getByText('源码'))
    expect(container.querySelector('pre')?.textContent).toBe(tableMd)
  })

  it('整段修订走行尾 ✎（走 onEditMarkdown → setSegmentMarkdown 保痕迹）', () => {
    const onEditMarkdown = vi.fn()
    const { container, getByLabelText, getByText } = render(
      <SegmentMarkdown {...base({ onEditMarkdown })} />,
    )
    fireEvent.click(getByLabelText('编辑整段'))
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '# 律师核过的正文' } })
    fireEvent.click(getByText('保存整段'))
    expect(onEditMarkdown).toHaveBeenCalledExactlyOnceWith('# 律师核过的正文')
  })

  /**
   * 编辑态把 tab 行整行收起：点 tab 会直接卸载 textarea，等于静默丢掉没保存的正文。
   * 编辑态自己的「保存整段 / 取消」才是出口。
   */
  it('编辑中不渲染 tab 行（避免点一下就丢掉未保存的正文）', () => {
    const { getByLabelText, queryByText, getByText } = render(
      <SegmentMarkdown {...base({ onEditMarkdown: vi.fn() })} />,
    )
    fireEvent.click(getByLabelText('编辑整段'))
    expect(getByText('保存整段')).toBeTruthy()
    expect(queryByText('分块')).toBeNull()
    expect(queryByText('渲染')).toBeNull()
    expect(queryByText('源码')).toBeNull()
  })

  it('没有 onEditMarkdown（只读）时不出现 ✎ 入口', () => {
    const { queryByLabelText } = render(<SegmentMarkdown {...base()} />)
    expect(queryByLabelText('编辑整段')).toBeNull()
  })

  it('块改动没同步进正文时给出提示，折叠态也看得见', () => {
    const { getByText } = render(
      <SegmentMarkdown {...base({ open: false, seg: seg({ md: tableMd, blocks, mdDrift: true }) })} />,
    )
    expect(getByText(/没能同步进 Markdown 正文/)).toBeTruthy()
  })

  it('没有 mdDrift 时不渲染该提示（不制造噪声）', () => {
    const { queryByText } = render(<SegmentMarkdown {...base()} />)
    expect(queryByText(/没能同步进 Markdown 正文/)).toBeNull()
  })

  it('没有定位块的段默认落到渲染视图（渲染结构，不再是纯文本 pre）', () => {
    const { container } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: tableMd, blocks: undefined }) })} />,
    )
    expect(container.querySelector('table')).toBeTruthy()
  })
})

/**
 * 页级识别风险（退化页 / 列数突变页）。
 *
 * 两条都是「任务成功、正文也生成了，但机器读出来的东西本身可疑」：
 * - 退化页：云端把该页读成复读循环、正文被清空，已换识别路径重取；
 * - 列数突变页：该页表格列数与上一页不同，数字可能挂到错的表头下。
 * 落点与证件 / 图纸同一套（该页正文第一行之前）；退化页常常整页没有正文，
 * 这时必须补在正文之后，否则等于没提示。
 */
describe('质量提示条（页级识别风险）', () => {
  it('退化页：文案逐字，且挂在该页正文第一行之前', () => {
    const { container, getByText } = render(<SegmentMarkdown {...base({ degeneratePages: [1] })} />)
    const hint = container.querySelector('[data-degenerate-hint]') as HTMLElement
    expect(hint.textContent).toBe('P1 云端取字判为退化，已换识别路径重取 · 建议核对原页')
    const firstRow = getByText('原告提交了转账凭证。')
    expect(hint.compareDocumentPosition(firstRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('列数突变页：写明本页几列 vs 上一页几列，页号沿用 P 写法', () => {
    const { container } = render(
      <SegmentMarkdown
        {...base({ columnAnomalies: [{ page_no: 1, prev_page_no: 8, cols: 5, prev_cols: 4 }] })}
      />,
    )
    const hint = container.querySelector('[data-column-anomaly-hint]') as HTMLElement
    expect(hint.textContent).toBe('P1 表格 5 列，上一页 P8 为 4 列 · 列可能被并/拆或换了模板，请核对数字表头')
  })

  /**
   * 没有定位块（后端是本地 OCR 时 positioned 为空）的段会被归一成「渲染视图」，
   * 那时**所有**提示页都进 orphan。渲染门若只认 `tab === 'blocks'`，这条路径
   * 一条提示都没有——而本地兜底恰恰是退化页最常落到的场景。
   */
  it('没有定位块的段（本地 OCR）里，退化页提示仍然出现', () => {
    const { container } = render(
      <SegmentMarkdown {...base({ seg: seg({ md: '# 证据目录\n\n原告提交了转账凭证。' }), degeneratePages: [1] })} />,
    )
    const hint = container.querySelector('[data-degenerate-hint]') as HTMLElement
    expect(hint).toBeTruthy()
    expect(hint.textContent).toContain('已换识别路径重取')
  })

  /** 关键回归：退化页往往整页没有正文（云端正文被清空），不纳入 orphan 就永远看不到提示 */
  it('退化页整页没有正文时，提示仍然出现（补在正文之后）', () => {
    const { container, getByText } = render(<SegmentMarkdown {...base({ degeneratePages: [147] })} />)
    const hint = container.querySelector('[data-degenerate-hint]') as HTMLElement
    expect(hint).toBeTruthy()
    const lastRow = getByText('被告对此不予认可。')
    expect(lastRow.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('点退化页提示条跳到那一页；退化排在图纸之前（正文不可信 > 内容不完整）', () => {
    const onGotoPage = vi.fn()
    const { container } = render(<SegmentMarkdown {...base({ degeneratePages: [1], graphicPages: [1], onGotoPage })} />)
    const degenerate = container.querySelector('[data-degenerate-hint]') as HTMLElement
    const graphic = container.querySelector('[data-quality-hint]') as HTMLElement
    expect(degenerate.compareDocumentPosition(graphic) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    fireEvent.click(degenerate)
    expect(onGotoPage).toHaveBeenCalledWith(1)
  })

  it('旧任务的草稿没有 pageAnomaly：不多一条提示（与引入前逐字一致）', () => {
    const { container } = render(<SegmentMarkdown {...base()} />)
    expect(container.querySelector('[data-degenerate-hint]')).toBeNull()
    expect(container.querySelector('[data-column-anomaly-hint]')).toBeNull()
    expect(container.querySelectorAll('[data-quality-hint]')).toHaveLength(0)
    expect(container.querySelectorAll('[data-doc-hint]')).toHaveLength(0)
  })
})
