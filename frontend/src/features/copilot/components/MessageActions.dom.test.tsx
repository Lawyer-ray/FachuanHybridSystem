// @vitest-environment jsdom
/**
 * 消息级操作条测试（jsdom）。
 *
 * 锁死的是**交互语义**，不是样式：
 * - 不可评分时按钮「可见但不可用」——`aria-disabled` + `aria-describedby` 指到一句
 *   具体原因（不是原生 disabled：那样收不到 hover/focus，原因永远弹不出来）；
 * - 可评分时点击真的下发 `rateMessage`，再点同一个是取消（`'none'`）；
 * - 时间戳按 `formatClock` 渲染，`dateTime` 带 ISO 供读屏/复制；
 * - 复制分两路：Markdown 源码（原样）与纯文本（去标记，贴到 Word 里不难看）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const copySpy = vi.hoisted(() => vi.fn(async (_text: string) => true))
vi.mock('@/lib/clipboard', () => ({ copyText: copySpy }))

import { MessageActions } from './MessageActions'
import { useCopilot } from '../store'

const MARKDOWN = '**合同总体**\n\n- 总数 **165** 份\n- 在办 `list_contracts`\n\n| 类别 | 数量 |\n| --- | --- |\n| 在办 | 165 |\n'

const rateSpy = vi.fn(async () => {})
const originalRate = useCopilot.getState().rateMessage

beforeEach(() => {
  copySpy.mockClear()
  rateSpy.mockClear()
  useCopilot.setState({ rateMessage: rateSpy })
})

afterEach(() => {
  useCopilot.setState({ rateMessage: originalRate })
})

/** 取按钮的原因文本（aria-describedby → 元素内容） */
function reasonOf(button: HTMLElement): string {
  const id = button.getAttribute('aria-describedby')
  expect(id).toBeTruthy()
  const el = document.getElementById(id!)
  expect(el).not.toBeNull()
  return el!.textContent ?? ''
}

describe('MessageActions：评分不可用时的说明', () => {
  it('未落库（messageId=null）：两侧评分按钮 aria-disabled 且挂具体原因', () => {
    const { container } = render(<MessageActions content="答" messageId={null} />)

    for (const name of ['有帮助', '没帮助']) {
      const button = screen.getByRole('button', { name })
      expect(button.getAttribute('aria-disabled')).toBe('true')
      // 原因必须具体到「为什么」+「怎么办」，而不是「不可用」
      expect(reasonOf(button)).toContain('还没落库')
      expect(reasonOf(button)).toContain('刷新')
      // 原生 disabled 收不到 hover/focus，tooltip 与读屏就都废了
      expect(button.hasAttribute('disabled')).toBe(false)
    }
    container.remove()
  })

  it('未落库时点击不下发请求（避免 NaN 主键打到后端）', () => {
    const { container } = render(<MessageActions content="答" messageId={null} />)

    fireEvent.click(screen.getByRole('button', { name: '有帮助' }))

    expect(rateSpy).not.toHaveBeenCalled()
    container.remove()
  })

  it('可评分时没有 aria-disabled / 不对原因做关联', () => {
    const { container } = render(<MessageActions content="答" messageId={12} />)

    const button = screen.getByRole('button', { name: '有帮助' })
    expect(button.hasAttribute('aria-disabled')).toBe(false)
    expect(button.hasAttribute('aria-describedby')).toBe(false)
    container.remove()
  })
})

describe('MessageActions：评分下发', () => {
  it('点赞下发 up，已点赞再点一下取消（none）', () => {
    const { container, rerender } = render(<MessageActions content="答" messageId={12} />)

    fireEvent.click(screen.getByRole('button', { name: '有帮助' }))
    expect(rateSpy).toHaveBeenLastCalledWith(12, 'up')

    rerender(<MessageActions content="答" messageId={12} rating="up" />)
    fireEvent.click(screen.getByRole('button', { name: '有帮助' }))
    expect(rateSpy).toHaveBeenLastCalledWith(12, 'none')
    container.remove()
  })

  it('点踩下发 down', () => {
    const { container } = render(<MessageActions content="答" messageId={7} />)
    fireEvent.click(screen.getByRole('button', { name: '没帮助' }))
    expect(rateSpy).toHaveBeenLastCalledWith(7, 'down')
    container.remove()
  })
})

describe('MessageActions：时间戳', () => {
  it('按 HH:mm 渲染，并带 ISO dateTime 与完整时刻 title', () => {
    const createdAt = new Date(2026, 4, 6, 9, 7).getTime()
    const { container } = render(<MessageActions content="答" messageId={1} createdAt={createdAt} />)

    const time = container.querySelector('time')
    expect(time?.textContent).toBe('09:07')
    expect(time?.getAttribute('dateTime')).toBe(new Date(createdAt).toISOString())
    expect(time?.getAttribute('title')).toContain('2026')
    container.remove()
  })

  it('没有 createdAt 时不渲染时间元素（旧数据不编造时刻）', () => {
    const { container } = render(<MessageActions content="答" messageId={1} />)
    expect(container.querySelector('time')).toBeNull()
    container.remove()
  })
})

describe('MessageActions：复制', () => {
  it('复制回答 = Markdown 源码原样', () => {
    const { container } = render(<MessageActions content={MARKDOWN} messageId={1} />)
    fireEvent.click(screen.getByRole('button', { name: '复制回答' }))
    expect(copySpy).toHaveBeenLastCalledWith(MARKDOWN)
    container.remove()
  })

  it('复制纯文本 = 去掉 Markdown 标记，但一个字都不丢', () => {
    const { container } = render(<MessageActions content={MARKDOWN} messageId={1} />)
    fireEvent.click(screen.getByRole('button', { name: '复制纯文本' }))

    const copied = copySpy.mock.calls.at(-1)?.[0] as string
    expect(copied).toContain('合同总体')
    expect(copied).toContain('总数 165 份')
    expect(copied).toContain('在办 list_contracts')
    expect(copied).not.toContain('**')
    expect(copied).not.toContain('| --- |')
    container.remove()
  })
})

/** 复制纯文本的整形规则：只剥结构标记，一个字都不能丢 */
describe('复制纯文本的整形', () => {
  it.each([
    ['## 一、结论', '一、结论'],
    ['> 引用的法条', '引用的法条'],
    ['1. 第一点', '第一点'],
    ['- 要点', '要点'],
    ['见 [民法典](https://x.test/a) 第 1 条', '见 民法典 第 1 条'],
    ['![图示](a.png)', '图示'],
    ['```ts\nconst a = 1\n```', 'const a = 1'],
    // 空行压成一段（Markdown 空两行分段，粘到 Word 里会变成大空隙）
    ['甲\n\n\n\n乙', '甲\n\n乙'],
    // **不能吃字符**：`_` 是标识符/文件名的一部分（# 无条件删标记的回归）
    ['在办 list_contracts', '在办 list_contracts'],
    ['附件：合同_终稿.docx', '附件：合同_终稿.docx'],
  ])('「%s」→ 纯文本', (markdown, expected) => {
    const { container } = render(<MessageActions content={markdown} messageId={1} />)
    fireEvent.click(screen.getByRole('button', { name: '复制纯文本' }))
    expect(copySpy.mock.calls.at(-1)?.[0]).toBe(expected)
    container.remove()
  })
})
