// @vitest-environment jsdom
/**
 * 角标渲染 + 来源卡片（jsdom）。
 *
 * 锁的是四条「错了就是误导律师」的行为：
 * 1. 有引用表才渲染角标；没有引用表时 `[K1]` 原样当文本（点了没内容的角标比没有更糟）；
 * 2. 键盘可达：Enter 打开、Esc 关闭并把焦点还给角标；
 * 3. 定位措辞走 `pageSpanNote`——材料说「第 N 段（按解析分段）」，法条才说「第 N 页」；
 * 4. 流式半截 `[K` 时整段降级为纯文本，闭合后才包角标（避免编号从 1 跳到 12）。
 *
 * 表格复制也放在这里：`TableBlock` 只有经 `AssistantMarkdown` 的 components 映射
 * 才被使用，从这一层测才同时覆盖「映射接上了」与「TSV 格式对」。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 剪贴板：复制必须走 lib/clipboard（带非安全上下文兜底），这里只验证调用参数 */
const clipboardMock = vi.hoisted(() => ({ copyText: vi.fn(async () => true) }))
vi.mock('@/lib/clipboard', () => clipboardMock)

import type { CitationRef } from '../../domain/knowledge'
import { AssistantMarkdown } from '../AssistantMarkdown'

/** 造一条最小引用；只覆盖用例关心的字段 */
function cite(citeNo: number, patch: Partial<CitationRef> = {}): CitationRef {
  return { citeNo, kind: 'file', name: `材料${citeNo}.pdf`, ...patch }
}

/** 统一包一层 Router：卡片里的「在案件中打开」是 <Link>，没有 Router 会直接抛 */
function renderMarkdown(text: string, citations?: readonly CitationRef[], streaming = false) {
  return render(
    <MemoryRouter>
      <AssistantMarkdown text={text} streaming={streaming} citations={citations} />
    </MemoryRouter>,
  )
}

/** 角标按钮的无障碍名：`查看来源 ${citeNo}：${name}` */
function markButton(citeNo: number): HTMLElement | null {
  return screen.queryByRole('button', { name: new RegExp(`^查看来源 ${citeNo}：`) })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CitationMark：渲染与降级', () => {
  it('正文里的 [K1] 渲染成可点角标', () => {
    const { container } = renderMarkdown('结论见[K1]。', [cite(1, { name: '借款合同.pdf' })])
    const button = markButton(1)
    expect(button).not.toBeNull()
    // 原文的方括号字样被角标取代，不再以裸文本出现在正文里
    expect(container.textContent).not.toContain('[K1]')
    expect(button?.getAttribute('aria-haspopup')).toBe('dialog')
    expect(button?.getAttribute('aria-expanded')).toBe('false')
  })

  it('没有引用表时 [K1] 当普通文本（点开没内容的角标等于骗人）', () => {
    const { container } = renderMarkdown('结论见[K1]。')
    expect(markButton(1)).toBeNull()
    expect(container.textContent).toContain('[K1]')
  })

  it('引用表是空数组时同样不渲染角标', () => {
    const { container } = renderMarkdown('结论见[K1]。', [])
    expect(markButton(1)).toBeNull()
    expect(container.textContent).toContain('[K1]')
  })

  it('引用表里没有的编号不渲染角标（模型乱标 [K9]）', () => {
    const { container } = renderMarkdown('见[K1]与[K9]', [cite(1)])
    expect(markButton(1)).not.toBeNull()
    expect(markButton(9)).toBeNull()
    expect(container.textContent).toContain('[K9]')
  })

  it('[1] / [2021] 永远不是角标（法条年份被做成来源是安全事故）', () => {
    const { container } = renderMarkdown('《民法典》[2021] 版，见第[1]条', [cite(1)])
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(container.textContent).toContain('[2021]')
  })

  it('代码里的 [K1] 不包角标（那是代码，不是引用）', () => {
    const { container } = renderMarkdown('示例：`arr[K1]`', [cite(1)])
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(container.textContent).toContain('[K1]')
  })

  it('列表项 / 加粗里的标记也能包上（不只处理段落顶层文本）', () => {
    renderMarkdown('- **结论见[K1]**\n- 另见[K2]', [cite(1), cite(2)])
    expect(markButton(1)).not.toBeNull()
    expect(markButton(2)).not.toBeNull()
  })
})

describe('CitationMark：流式半截标记降级', () => {
  it('末尾还有半截 [K 时整段按纯文本渲染（角标既不闪也不换编号）', () => {
    const { container } = renderMarkdown('结论见[K1]，另见[K', [cite(1), cite(2)], true)
    expect(markButton(1)).toBeNull()
    expect(container.textContent).toContain('[K1]')
    expect(container.textContent).toContain('[K')
  })

  it('闭合后的下一帧恢复角标', () => {
    renderMarkdown('结论见[K1]，另见[K2]', [cite(1), cite(2)], true)
    expect(markButton(1)).not.toBeNull()
    expect(markButton(2)).not.toBeNull()
  })

  it('非流式（历史消息）末尾真有 [K 字样时，不影响同段已闭合的角标', () => {
    renderMarkdown('结论见[K1]，原文写的是 [K', [cite(1)], false)
    expect(markButton(1)).not.toBeNull()
  })
})

describe('CitationPopover：键盘与措辞', () => {
  it('Enter 打开卡片，卡片里报出来源名与定位', () => {
    renderMarkdown('结论见[K1]。', [cite(1, { name: '借款合同.pdf', page: 3 })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')

    fireEvent.keyDown(button, { key: 'Enter' })

    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('借款合同.pdf')
    // 材料文件的页是**解析分段**，不能写成「第 3 页」
    expect(dialog.textContent).toContain('第 3 段（按解析分段）')
    expect(dialog.textContent).not.toContain('第 3 页')
    expect(button.getAttribute('aria-expanded')).toBe('true')
  })

  it('点击也能打开（触摸 / 鼠标路径）', () => {
    renderMarkdown('结论见[K1]。', [cite(1)])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('Esc 关闭并把焦点还给角标（否则键盘用户要从正文第一个角标重新 Tab）', () => {
    renderMarkdown('结论见[K1]。', [cite(1)])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')

    fireEvent.click(button)
    expect(screen.getByRole('dialog')).toBeTruthy()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(button)
  })

  it('法条才说「第 N 页」（statute 的页号是印刷页语义）', () => {
    renderMarkdown('见[K1]。', [cite(1, { kind: 'statute', name: '民法典第 577 条', page: 3 })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog').textContent).toContain('第 3 页')
  })

  it('有条款号时优先报条款号（比页精确）', () => {
    renderMarkdown('见[K1]。', [cite(1, { kind: 'contract', clause: '7.2', page: 9 })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog').textContent).toContain('第 7.2 条')
  })

  it('没有原文时如实说「原文未随本轮保存」', () => {
    renderMarkdown('见[K1]。', [cite(1)])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog').textContent).toContain('原文未随本轮保存')
  })

  it('命中关键词时用 <mark> 高亮', () => {
    renderMarkdown('见[K1]。', [cite(1, { text: '甲方应于三十日内支付租金', keywords: ['租金'] })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog').querySelector('mark')?.textContent).toBe('租金')
  })

  it('关键词缺失时整段不高亮（不按空格瞎猜，把半段原文涂成荧光色）', () => {
    renderMarkdown('见[K1]。', [cite(1, { text: '甲方应于三十日内支付租金' })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.getByRole('dialog').querySelector('mark')).toBeNull()
  })

  it('案件引用给出「在案件中打开」，链接指向案件工作台', () => {
    renderMarkdown('见[K1]。', [cite(1, { kind: 'case', refId: 42, name: '（20XX）某01民初某某号' })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    const link = screen.getByRole('link', { name: '在案件中打开' })
    expect(link.getAttribute('href')).toBe('/bank-litigation/42')
  })

  it('法条引用不给跳转按钮（没有可跳的详情页，点了 404 比不给更糟）', () => {
    renderMarkdown('见[K1]。', [cite(1, { kind: 'statute', refId: 7, name: '民法典第 577 条' })])
    const button = markButton(1)
    if (button === null) throw new Error('应当渲染出角标')
    fireEvent.click(button)
    expect(screen.queryByRole('link')).toBeNull()
  })
})

describe('AssistantMarkdown：表格复制为 TSV', () => {
  it('复制的是制表符分列、换行分行（贴进 Excel 自动分列）', async () => {
    renderMarkdown('| 名称 | 金额 |\n| --- | --- |\n| 甲 | 100 |')
    fireEvent.click(screen.getByRole('button', { name: '复制表格' }))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    expect(clipboardMock.copyText).toHaveBeenCalledWith('名称\t金额\n甲\t100')
  })

  it('单元格里的行内格式被拆成纯文本（不能把 ** 或反引号粘进 Excel）', async () => {
    renderMarkdown('| 项目 | 金额 |\n| --- | --- |\n| **本金** | `100` |')
    fireEvent.click(screen.getByRole('button', { name: '复制表格' }))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    expect(clipboardMock.copyText).toHaveBeenCalledWith('项目\t金额\n本金\t100')
  })

  it('表格里的 [K1] 也能包角标（单元格走 td 映射）', () => {
    renderMarkdown('| 项目 | 依据 |\n| --- | --- |\n| 本金 | [K1] |', [cite(1)])
    expect(markButton(1)).not.toBeNull()
  })
})
