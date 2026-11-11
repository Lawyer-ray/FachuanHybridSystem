// @vitest-environment jsdom
/**
 * ReaderChrome 测试（jsdom）。
 *
 * 阅读器是 fixed inset 全屏层，两个 early-return 分支（加载中 / 打开失败）
 * 也要有完整外壳，否则出错时页面会变成一片没有退路的空白。这里钉住三条：
 * 1. 三个外壳都走同一个 FixedReader（右缘吃 --copilot-docked-w）；
 * 2. closing 时挂 `closing` 类（退场动画依赖它）；
 * 3. 点按钮不夺焦（mousedown preventDefault），否则回车会重触发按钮导致闪烁。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FixedReader, ReaderError, ReaderLoading } from './ReaderChrome'

describe('FixedReader', () => {
  it('渲染子节点并把 rootRef 挂到根容器', () => {
    const nodes: Array<HTMLDivElement | null> = []
    render(<FixedReader rootRef={(n) => nodes.push(n)}>内容</FixedReader>)
    expect(screen.getByText('内容')).toBeTruthy()
    expect(nodes[0]).toBeInstanceOf(HTMLDivElement)
  })

  it('closing 时带上 closing 类（退场动画依赖）', () => {
    const { container, rerender } = render(<FixedReader>内容</FixedReader>)
    const root = container.firstElementChild as HTMLElement
    expect(root.className).toContain('mp-reader')
    expect(root.className).not.toContain('closing')

    rerender(<FixedReader closing>内容</FixedReader>)
    expect((container.firstElementChild as HTMLElement).className).toContain('closing')
  })

  it('在按钮上按下鼠标不夺焦（避免回车重触发按钮造成闪烁）', () => {
    render(
      <FixedReader>
        <button type="button">工具栏按钮</button>
      </FixedReader>,
    )
    const btn = screen.getByRole('button', { name: '工具栏按钮' })
    const evt = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    btn.dispatchEvent(evt)
    expect(evt.defaultPrevented).toBe(true)
  })

  it('在非按钮区域按下鼠标不拦截默认行为（文本仍可正常选中）', () => {
    render(<FixedReader>正文文字</FixedReader>)
    const p = screen.getByText('正文文字')
    const evt = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    p.dispatchEvent(evt)
    expect(evt.defaultPrevented).toBe(false)
  })
})

describe('ReaderLoading', () => {
  it('给出「正在打开材料包」的等待文案', () => {
    render(<ReaderLoading />)
    expect(screen.getByText(/正在打开材料包，解析页数/)).toBeTruthy()
  })
})

describe('ReaderError', () => {
  it('展示错误文案，「返回」触发关闭', () => {
    const onBack = vi.fn()
    render(<ReaderError error="材料包已被删除" onBack={onBack} />)
    expect(screen.getByText('材料包已被删除')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '返回' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
