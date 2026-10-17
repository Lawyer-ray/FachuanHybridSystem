// @vitest-environment jsdom
/**
 * 阅读器横栏 / 段头的窄屏可达性 dom 测试（jsdom）。
 *
 * 手机没有键盘：取字 / 选页提示条要有真退出按钮；段头动作按钮图标化后无障碍名
 * 必须仍在，首段不渲染「并入上一份」。CSS 断点显隐 jsdom 看不见，这里只锁
 * 「按钮存在 + 回调正确」这层契约。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Segment } from '../../types'
import { HintBar } from './HintBar'
import { SegmentHeader } from './SegmentHeader'

describe('HintBar', () => {
  it('取字态：退出按钮文案「取消」，点击触发 onExit', () => {
    const onExit = vi.fn()
    render(<HintBar mode="pick" field="合同编号" onExit={onExit} />)
    fireEvent.click(screen.getByRole('button', { name: /取消/ }))
    expect(onExit).toHaveBeenCalledTimes(1)
  })

  it('选页态：退出按钮文案「退出」，点击触发 onExit', () => {
    const onExit = vi.fn()
    render(<HintBar mode="sel" onExit={onExit} />)
    fireEvent.click(screen.getByRole('button', { name: /退出/ }))
    expect(onExit).toHaveBeenCalledTimes(1)
  })
})

describe('SegmentHeader', () => {
  const seg: Segment = {
    id: 's1',
    t: '起诉状',
    fn: '赖某-移交诉讼材料',
    refs: [
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
    ],
    manual: false,
  }
  const noop = { onSetType: vi.fn(), onRename: vi.fn() }

  it('非首段：「并入上一份」按 aria-label 可定位（手机图标化后仍有名）并触发回调', () => {
    const onMerge = vi.fn()
    render(<SegmentHeader seg={seg} si={1} color="#0ea5e9" {...noop} onMerge={onMerge} />)
    fireEvent.click(screen.getByRole('button', { name: '并入上一份' }))
    expect(onMerge).toHaveBeenCalledTimes(1)
  })

  it('首段：没有上一份，不渲染「并入上一份」（不留永远点不了的灰按钮）', () => {
    render(<SegmentHeader seg={seg} si={0} color="#0ea5e9" {...noop} onMerge={vi.fn()} />)
    expect(screen.queryByRole('button', { name: '并入上一份' })).toBeNull()
  })

  it('段头标页区间 + 页数：同源「P1–2 · 2 页」，跨源「跨源 · 2 页」', () => {
    const { unmount } = render(<SegmentHeader seg={seg} si={1} color="#0ea5e9" {...noop} onMerge={vi.fn()} />)
    expect(screen.getByText('P1–2 · 2 页')).toBeTruthy()
    unmount()
    const cross: Segment = { ...seg, refs: [{ mi: 0, p: 1 }, { mi: 1, p: 1 }] }
    render(<SegmentHeader seg={cross} si={1} color="#0ea5e9" {...noop} onMerge={vi.fn()} />)
    expect(screen.getByText('跨源 · 2 页')).toBeTruthy()
  })
})
