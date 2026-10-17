// @vitest-environment jsdom
/**
 * 阅读器横栏 / 段头 / 左栏行的窄屏可达性 dom 测试（jsdom）。
 *
 * 手机没有键盘：取字 / 选页提示条要有真退出按钮；段头动作按钮图标化后无障碍名
 * 必须仍在，首段不渲染「并入上一份」；左栏行双击进入行内改名。CSS 断点显隐 jsdom
 * 看不见，这里只锁「按钮存在 + 回调正确」这层契约。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DraftState, Segment } from '../../types'
import { HintBar } from './HintBar'
import { Rail } from './Rail'
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
  const noop = { onRename: vi.fn() }

  it('非首段：「并入上一份」按 aria-label 可定位（手机图标化后仍有名）并触发回调', () => {
    const onMerge = vi.fn()
    render(<SegmentHeader seg={seg} si={1} color="#0ea5e9" classified {...noop} onMerge={onMerge} />)
    fireEvent.click(screen.getByRole('button', { name: '并入上一份' }))
    expect(onMerge).toHaveBeenCalledTimes(1)
  })

  it('首段：没有上一份，不渲染「并入上一份」（不留永远点不了的灰按钮）', () => {
    render(<SegmentHeader seg={seg} si={0} color="#0ea5e9" classified {...noop} onMerge={vi.fn()} />)
    expect(screen.queryByRole('button', { name: '并入上一份' })).toBeNull()
  })

  it('未归类：不再有类型胶囊控件，名字亮琥珀并提示改名词', () => {
    render(<SegmentHeader seg={{ ...seg, t: '' }} si={1} color="#0ea5e9" classified={false} {...noop} onMerge={vi.fn()} />)
    expect(screen.queryByText(/未归类/)).toBeNull()
    const nameBtn = screen.getByRole('button', { name: /赖某-移交诉讼材料/ })
    expect(nameBtn.className).toContain('text-amber-700')
  })

  it('段头标页区间 + 页数：同源「P1–2 · 2 页」，跨源「跨源 · 2 页」', () => {
    const { unmount } = render(<SegmentHeader seg={seg} si={1} color="#0ea5e9" classified {...noop} onMerge={vi.fn()} />)
    expect(screen.getByText('P1–2 · 2 页')).toBeTruthy()
    unmount()
    const cross: Segment = { ...seg, refs: [{ mi: 0, p: 1 }, { mi: 1, p: 1 }] }
    render(<SegmentHeader seg={cross} si={1} color="#0ea5e9" classified {...noop} onMerge={vi.fn()} />)
    expect(screen.getByText('跨源 · 2 页')).toBeTruthy()
  })
})

describe('Rail 左栏行', () => {
  const draft: DraftState = {
    mats: [{ partIndex: 0, n: '扫描.pdf', k: 'pdf', pages: 5 }],
    segs: [
      { id: 's0', t: '起诉状', fn: '起诉状.pdf', refs: [{ mi: 0, p: 1 }], manual: true },
      { id: 's1', t: '', fn: '扫描-P2.pdf', refs: [{ mi: 0, p: 2 }, { mi: 0, p: 3 }], manual: true },
    ],
    infos: [],
  }

  function renderRail(over: Partial<Parameters<typeof Rail>[0]> = {}) {
    const handlers = { onFocusSeg: vi.fn(), onRenameMat: vi.fn(), onRenameSeg: vi.fn(), onSetSegType: vi.fn(), onMergeSeg: vi.fn(), onMergeSegs: vi.fn(), onMoveSeg: vi.fn() }
    render(<Rail draft={draft} {...handlers} {...over} />)
    return handlers
  }

  it('点行跳转该段；行标页区间', () => {
    const { onFocusSeg } = renderRail()
    fireEvent.click(screen.getByText('起诉状.pdf'))
    expect(onFocusSeg).toHaveBeenCalledWith(0)
    expect(screen.getByText('P2–3')).toBeTruthy()
  })

  it('双击行 → 行内输入框改名，Enter 提交 onRenameSeg', () => {
    const { onRenameSeg } = renderRail()
    fireEvent.doubleClick(screen.getByText('扫描-P2.pdf'))
    const input = screen.getByLabelText('材料名') as HTMLInputElement
    expect(input.value).toBe('扫描-P2.pdf')
    fireEvent.change(input, { target: { value: '身份证.pdf' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRenameSeg).toHaveBeenCalledWith(1, '身份证.pdf')
  })

  it('行内改名按 Esc 取消，不提交', () => {
    const { onRenameSeg } = renderRail()
    fireEvent.doubleClick(screen.getByText('扫描-P2.pdf'))
    const input = screen.getByLabelText('材料名')
    fireEvent.change(input, { target: { value: '身份证.pdf' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRenameSeg).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('材料名')).toBeNull()
  })
})
