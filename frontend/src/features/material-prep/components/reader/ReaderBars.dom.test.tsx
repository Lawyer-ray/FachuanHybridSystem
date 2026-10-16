// @vitest-environment jsdom
/**
 * 阅读器三条横栏的窄屏可达性 dom 测试（jsdom）。
 *
 * 手机没有键盘：底栏要有真「完成拆分与归类」按钮、取字 / 选页提示条要有真退出按钮，
 * 段头动作按钮图标化后无障碍名必须仍在。CSS 断点显隐 jsdom 看不见，这里只锁
 * 「按钮存在 + 回调正确」这层契约。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Segment } from '../../types'
import { HintBar } from './HintBar'
import { KeyHintsBar } from './KeyHintsBar'
import { SegmentHeader } from './SegmentHeader'

describe('KeyHintsBar', () => {
  it('渲染「完成拆分与归类」按钮，点击触发 onComplete', () => {
    const onComplete = vi.fn()
    render(<KeyHintsBar allClassified unclassified={0} onComplete={onComplete} />)
    expect(screen.getByText('全部已归类，可以归案了')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /完成拆分与归类/ }))
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('未归类时显示剩余段数', () => {
    render(<KeyHintsBar allClassified={false} unclassified={3} onComplete={vi.fn()} />)
    expect(screen.getByText('还有 3 段没归类')).toBeTruthy()
  })
})

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

describe('SegmentHeader 动作按钮无障碍名（手机图标化后仍可按名定位）', () => {
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

  it('并入上一份 / 拆分为文件 按 aria-label 可定位并触发回调', () => {
    const onMerge = vi.fn()
    const onToggleDone = vi.fn()
    render(
      <SegmentHeader seg={seg} si={1} color="#0ea5e9" onSetType={vi.fn()} onRename={vi.fn()} onMerge={onMerge} onToggleDone={onToggleDone} />,
    )
    fireEvent.click(screen.getByRole('button', { name: '并入上一份' }))
    expect(onMerge).toHaveBeenCalledTimes(1)
    const done = screen.getByRole('button', { name: '拆分为文件' })
    expect(done.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(done)
    expect(onToggleDone).toHaveBeenCalledTimes(1)
  })

  it('已拆分态：无障碍名切换为「已拆分为文件」且 aria-pressed=true；首段「并入上一份」禁用', () => {
    render(
      <SegmentHeader seg={{ ...seg, done: true }} si={0} color="#0ea5e9" onSetType={vi.fn()} onRename={vi.fn()} onMerge={vi.fn()} onToggleDone={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: '已拆分为文件' }).getAttribute('aria-pressed')).toBe('true')
    expect((screen.getByRole('button', { name: '并入上一份' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
