// @vitest-environment jsdom
/**
 * 「选中即引用」浮条测试（jsdom）。
 *
 * 四条不变量，每条都对应一个真实会出错的路径：
 * - **只在正文容器内的选区才出现**：浏览器允许选区横跨文档，从回答拖到输入框
 *   会产出一段「半截在别处」的文字，不清掉就会把假引用塞进输入框；
 * - **引用 = `setPendingQuote`**（复用已有动作），且会话没有案件/合同归属时
 *   「可见但不可用」+ 具体原因，而不是编一个 `case_id=0` 出去；
 * - **Esc 能关**（键盘用户没有别的退路），且浮条出现时不抢焦点；
 * - **定位夹在可见框内**：长回答里选中靠底部的文字，浮条不能被输入框盖住。
 *
 * 假 rect：jsdom 不做布局，所有矩形都是 0。所以这里直接给 Range / 元素塞
 * 矩形，验证的是**定位算法**，不是浏览器排版。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SelectionBarLayer } from './SelectionBar'
import { MessageList } from './MessageList'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'

type FakeRect = {
  top: number
  left: number
  right: number
  bottom: number
  width: number
  height: number
}

function fakeRect(partial: Partial<FakeRect> = {}): DOMRect {
  const top = partial.top ?? 0
  const left = partial.left ?? 0
  const width = partial.width ?? 0
  const height = partial.height ?? 0
  return {
    top,
    left,
    width,
    height,
    right: partial.right ?? left + width,
    bottom: partial.bottom ?? top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect
}

/** 给某个元素装上假矩形（jsdom 里直接覆盖实例方法，不影响其它元素） */
function stubRect(el: Element, rect: Partial<FakeRect>) {
  Object.defineProperty(el, 'getBoundingClientRect', { value: () => fakeRect(rect), configurable: true })
}

let rangeRect: Partial<FakeRect> = { top: 100, left: 100, width: 200, height: 20 }

beforeEach(() => {
  rangeRect = { top: 100, left: 100, width: 200, height: 20 }
  // jsdom 根本不实现 Range.getBoundingClientRect（只有真浏览器有），这里补上假矩形
  Object.defineProperty(Range.prototype, 'getBoundingClientRect', {
    value: () => fakeRect(rangeRect),
    configurable: true,
  })
  useCopilot.setState({
    context: { origin: 'contract', refId: 88, title: '某某借款合同' },
    pendingQuote: null,
    messages: [],
    streaming: false,
    loadingHistory: false,
    approvals: [],
    lastError: null,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  delete (Range.prototype as any).getBoundingClientRect
  window.getSelection()?.removeAllRanges()
})

/** 选中某节点里的全部文字，并按当前假 rect 触发一次 mouseup（= 拖选结束） */
function select(node: Node) {
  const range = document.createRange()
  range.selectNodeContents(node)
  const selection = window.getSelection()!
  selection.removeAllRanges()
  selection.addRange(range)
  fireEvent.mouseUp(document)
}

function Harness() {
  return (
    <div>
      <div data-copilot-scroll data-testid="scroll">
        <div data-copilot-selection-root data-testid="body">
          甲方应于合同签订之日起三十日内支付全部价款。
        </div>
      </div>
      <div data-testid="outside">输入框外的普通文字</div>
      <SelectionBarLayer />
    </div>
  )
}

describe('SelectionBar：何时出现', () => {
  it('没有选区时不存在', () => {
    const { container } = render(<Harness />)
    expect(screen.queryByTestId('selection-bar')).toBeNull()
    container.remove()
  })

  it('选区在正文容器内 → 出现', () => {
    const { container } = render(<Harness />)

    select(screen.getByTestId('body').firstChild!)

    expect(screen.getByTestId('selection-bar')).toBeTruthy()
    container.remove()
  })

  it('选区在正文容器外 → 不出现（不允许把别处的文字当引用）', () => {
    const { container } = render(<Harness />)

    select(screen.getByTestId('outside').firstChild!)

    expect(screen.queryByTestId('selection-bar')).toBeNull()
    container.remove()
  })

  it('选区被清空（点别处）后浮条收起', () => {
    const { container } = render(<Harness />)
    select(screen.getByTestId('body').firstChild!)
    expect(screen.getByTestId('selection-bar')).toBeTruthy()

    window.getSelection()!.removeAllRanges()
    fireEvent(document, new Event('selectionchange'))

    expect(screen.queryByTestId('selection-bar')).toBeNull()
    container.remove()
  })

  it('消息正文真的带上了生效范围标记（MessageList 接线）', () => {
    const messages: ChatMessage[] = [{ id: 'db-2', role: 'assistant', content: '答案是 **三十日**。', serverId: 2 }]
    useCopilot.setState({ messages })
    const { container } = render(<MessageList />)

    const root = container.querySelector('[data-copilot-selection-root]')
    expect(root).not.toBeNull()
    select(root!.firstChild ?? root!)

    expect(screen.getByTestId('selection-bar')).toBeTruthy()
    container.remove()
  })
})

describe('SelectionBar：引用到输入框', () => {
  it('点击「引用到输入框」写入 store.pendingQuote（新选区覆盖旧选区）', () => {
    const { container } = render(<Harness />)
    select(screen.getByTestId('body').firstChild!)

    fireEvent.click(screen.getByRole('button', { name: '引用到输入框' }))

    const quote = useCopilot.getState().pendingQuote
    expect(quote?.text).toBe('甲方应于合同签订之日起三十日内支付全部价款。')
    // 归属来自会话的业务范围（真实案件/合同 id），不是从消息 id 编的
    expect(quote?.kind).toBe('contract')
    expect(quote?.ownerId).toBe(88)
    // 引用完浮条自己收起（选区也已清掉，不会复活）
    expect(screen.queryByTestId('selection-bar')).toBeNull()
    container.remove()
  })

  it('会话没有业务归属时按钮可见但不可用，并说明原因（不编造 case_id）', () => {
    useCopilot.setState({ context: null })
    const { container } = render(<Harness />)
    select(screen.getByTestId('body').firstChild!)

    const button = screen.getByRole('button', { name: '引用到输入框' })
    expect(button.getAttribute('aria-disabled')).toBe('true')
    const reasonId = button.getAttribute('aria-describedby')
    expect(reasonId).toBeTruthy()
    expect(document.getElementById(reasonId!)?.textContent).toContain('没有关联的案件或合同')

    fireEvent.click(button)
    expect(useCopilot.getState().pendingQuote).toBeNull()
    container.remove()
  })
})

describe('SelectionBar：键盘', () => {
  it('Esc 关掉浮条', () => {
    const { container } = render(<Harness />)
    select(screen.getByTestId('body').firstChild!)
    expect(screen.getByTestId('selection-bar')).toBeTruthy()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByTestId('selection-bar')).toBeNull()
    container.remove()
  })

  it('输入法组合期的 Esc 不误关（那是取消候选，不是关浮条）', () => {
    const { container } = render(<Harness />)
    select(screen.getByTestId('body').firstChild!)

    fireEvent.keyDown(document, { key: 'Escape', isComposing: true })

    expect(screen.getByTestId('selection-bar')).toBeTruthy()
    container.remove()
  })

  it('浮条出现不抢焦点（选区还在编辑器/正文里，Tab 顺序不变）', () => {
    const { container } = render(<Harness />)
    const active = document.activeElement

    select(screen.getByTestId('body').firstChild!)

    expect(document.activeElement).toBe(active)
    container.remove()
  })
})

describe('SelectionBar：定位夹在可见框内', () => {
  it('选区靠底部（下方就是输入框）→ 翻到选区上方，不越过可视下边界', () => {
    const { container } = render(<Harness />)
    stubRect(screen.getByTestId('scroll'), { top: 0, left: 0, width: 1024, height: 768 })
    // 选区在 740~760：下方紧贴视口下沿
    rangeRect = { top: 740, width: 200, height: 20 }

    select(screen.getByTestId('body').firstChild!)

    const bar = screen.getByTestId('selection-bar')
    const top = Number.parseFloat(bar.style.top)
    expect(bar.dataset.placement).toBe('above')
    // 可见框下边界 768，浮条高 30（jsdom 量不到尺寸 → 走保守估算）+ 8 间距
    expect(top).toBeLessThanOrEqual(768 - 30 - 8)
    expect(top).toBeGreaterThanOrEqual(0)
    container.remove()
  })

  it('输入框占位把下边界抬高：浮条不会压在输入区上', () => {
    const { container } = render(
      <div>
        <div data-copilot-scroll data-testid="scroll">
          <div data-copilot-selection-root data-testid="body">甲方应于三十日内付款。</div>
        </div>
        <textarea data-testid="composer" />
        <SelectionBarLayer />
      </div>,
    )
    stubRect(screen.getByTestId('scroll'), { top: 0, left: 0, width: 1024, height: 768 })
    stubRect(screen.getByTestId('composer'), { top: 700, width: 600, height: 40 })
    rangeRect = { top: 640, width: 200, height: 20 }

    select(screen.getByTestId('body').firstChild!)

    const top = Number.parseFloat(screen.getByTestId('selection-bar').style.top)
    // 输入区上沿 700 减去「浮条高 30 + 间距 8」就是浮条下沿的上限
    expect(top).toBeLessThanOrEqual(700 - 30 - 8)
    container.remove()
  })

  it('转录里的 textarea（提问卡）不会被当成输入区座位', () => {
    const { container } = render(
      <div>
        <div data-copilot-scroll data-testid="scroll">
          <div data-copilot-selection-root data-testid="body">甲方应于三十日内付款。</div>
          {/* 结构化提问卡里的输入框：也在消息区，不能拿它当输入区座位 */}
          <textarea data-testid="question-card" />
        </div>
        <textarea data-testid="composer" />
        <SelectionBarLayer />
      </div>,
    )
    stubRect(screen.getByTestId('scroll'), { top: 0, left: 0, width: 1024, height: 768 })
    stubRect(screen.getByTestId('question-card'), { top: 380, width: 600, height: 40 })
    stubRect(screen.getByTestId('composer'), { top: 700, width: 600, height: 40 })
    rangeRect = { top: 620, width: 200, height: 20 }

    select(screen.getByTestId('body').firstChild!)

    const bar = screen.getByTestId('selection-bar')
    // 下边界按真正输入区（700）算：648 放得下 → 仍在选区下方；
    // 若误把提问卡（380）当座位，就会被夹到 362 并翻到上方
    expect(bar.dataset.placement).toBe('below')
    expect(Number.parseFloat(bar.style.top)).toBe(640 + 8)
    container.remove()
  })

  it('选区在可见框内、下方放得下 → 放选区下方', () => {
    const { container } = render(<Harness />)
    stubRect(screen.getByTestId('scroll'), { top: 0, left: 0, width: 1024, height: 768 })
    rangeRect = { top: 100, width: 200, height: 20 }

    select(screen.getByTestId('body').firstChild!)

    const bar = screen.getByTestId('selection-bar')
    expect(bar.dataset.placement).toBe('below')
    expect(Number.parseFloat(bar.style.top)).toBe(120 + 8)
    container.remove()
  })

  it('水平方向夹进取景框（贴右边选的文字不会把浮条推到屏幕外）', () => {
    const { container } = render(<Harness />)
    stubRect(screen.getByTestId('scroll'), { top: 0, left: 0, width: 1024, height: 768 })
    rangeRect = { top: 100, left: 1000, width: 20, height: 20 }

    select(screen.getByTestId('body').firstChild!)

    const left = Number.parseFloat(screen.getByTestId('selection-bar').style.left)
    expect(left).toBeLessThanOrEqual(1024 - 132 - 8)
    container.remove()
  })
})
