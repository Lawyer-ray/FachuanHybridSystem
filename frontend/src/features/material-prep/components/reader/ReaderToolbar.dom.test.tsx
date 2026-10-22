// @vitest-environment jsdom
/**
 * ReaderToolbar 测试（jsdom）。
 *
 * 阅读器工具组，两条分支维度：
 * - narrow（<1100px）多出「材料 / 信息」两个抽屉开关；非 narrow 不渲染它们
 * - inline（嵌入顶栏）只输出按钮组；非 inline 自带容器
 *
 * 各按钮的 on/off 态、禁用态、自动分段的忙碌文案，以及「恢复初始分段」
 * 收在 ⋯ 菜单里防误触。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReaderToolbar } from './ReaderToolbar'

type ToolbarProps = React.ComponentProps<typeof ReaderToolbar>

function makeProps(over: Partial<ToolbarProps> = {}): ToolbarProps {
  return {
    narrow: false,
    railOpen: false,
    metaOpen: false,
    onToggleRail: vi.fn(),
    onToggleMeta: vi.fn(),
    selMode: false,
    onToggleSelMode: vi.fn(),
    onAddFiles: vi.fn(),
    zoomVal: 100,
    onZoomIn: vi.fn(),
    onZoomOut: vi.fn(),
    onZoomReset: vi.fn(),
    cols: 1,
    colsDisabled: false,
    onChangeCols: vi.fn(),
    onResetSegments: vi.fn(),
    onAutoSplit: vi.fn(),
    autoSplitRunning: false,
    autoSplitProgress: '',
    ...over,
  }
}

function renderToolbar(over: Partial<ToolbarProps> = {}) {
  const props = makeProps(over)
  const utils = render(<ReaderToolbar {...props} />)
  return Object.assign(utils, { props })
}

describe('ReaderToolbar：narrow 分支', () => {
  it('narrow 时渲染「材料 / 信息」抽屉开关', () => {
    const { unmount } = renderToolbar({ narrow: true })
    expect(screen.getByRole('button', { name: '材料' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '信息' })).toBeTruthy()
    unmount()
  })

  it('非 narrow 时不渲染抽屉开关', () => {
    const { unmount } = renderToolbar({ narrow: false })
    expect(screen.queryByRole('button', { name: '材料' })).toBeNull()
    expect(screen.queryByRole('button', { name: '信息' })).toBeNull()
    unmount()
  })

  it('抽屉开关点击回调', () => {
    const { props, unmount } = renderToolbar({ narrow: true })
    fireEvent.click(screen.getByRole('button', { name: '材料' }))
    fireEvent.click(screen.getByRole('button', { name: '信息' }))
    expect(props.onToggleRail).toHaveBeenCalled()
    expect(props.onToggleMeta).toHaveBeenCalled()
    unmount()
  })

  it('railOpen / metaOpen 时开关带激活态', () => {
    const { unmount } = renderToolbar({ narrow: true, railOpen: true, metaOpen: true })
    expect(screen.getByRole('button', { name: '材料' }).className).toContain('bg-')
    unmount()
  })
})

describe('ReaderToolbar：核心按钮', () => {
  it('选页按钮点击与激活态', () => {
    const { props, unmount } = renderToolbar({ selMode: true })
    const btn = screen.getByRole('button', { name: '选页' })
    fireEvent.click(btn)
    expect(props.onToggleSelMode).toHaveBeenCalled()
    expect(btn.className).toContain('bg-')
    unmount()
  })

  it('追加材料按钮回调', () => {
    const { props, unmount } = renderToolbar()
    fireEvent.click(screen.getByRole('button', { name: /追加材料/ }))
    expect(props.onAddFiles).toHaveBeenCalled()
    unmount()
  })

  it('缩放三件套各自回调', () => {
    const { props, unmount } = renderToolbar()
    fireEvent.click(screen.getByRole('button', { name: '缩小画布' }))
    fireEvent.click(screen.getByRole('button', { name: '放大画布' }))
    fireEvent.click(screen.getByRole('button', { name: /100%/ }))
    expect(props.onZoomOut).toHaveBeenCalled()
    expect(props.onZoomIn).toHaveBeenCalled()
    expect(props.onZoomReset).toHaveBeenCalled()
    unmount()
  })

  it('缩放百分比按 zoomVal 渲染', () => {
    const { unmount } = renderToolbar({ zoomVal: 150 })
    expect(screen.getByRole('button', { name: /150%/ })).toBeTruthy()
    unmount()
  })

  it('列数按钮：可用时点击回调', () => {
    const { props, unmount } = renderToolbar({ cols: 2, colsDisabled: false })
    const btn = screen.getByRole('button', { name: /并排列数：当前 2 列/ })
    fireEvent.click(btn)
    expect(props.onChangeCols).toHaveBeenCalled()
    unmount()
  })

  it('列数按钮：colsDisabled 时禁用', () => {
    const { props, unmount } = renderToolbar({ colsDisabled: true })
    const btn = screen.getByRole('button', { name: /并排列数/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(props.onChangeCols).not.toHaveBeenCalled()
    unmount()
  })
})

describe('ReaderToolbar：自动分段', () => {
  it('空闲时显示「自动分段」并可点', () => {
    const { props, unmount } = renderToolbar()
    fireEvent.click(screen.getByRole('button', { name: '自动分段' }))
    expect(props.onAutoSplit).toHaveBeenCalled()
    unmount()
  })

  it('运行中禁用并显示进度文案', () => {
    const { unmount } = renderToolbar({ autoSplitRunning: true, autoSplitProgress: '识别 3/10' })
    const btn = screen.getByRole('button', { name: /识别 3\/10/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    unmount()
  })

  it('运行中无进度时回退「识别中…」', () => {
    const { unmount } = renderToolbar({ autoSplitRunning: true, autoSplitProgress: '' })
    expect(screen.getByRole('button', { name: /识别中…/ })).toBeTruthy()
    unmount()
  })
})

describe('ReaderToolbar：更多操作菜单', () => {
  it('⋯ 菜单里能触发「恢复初始分段」', async () => {
    const { props, unmount } = renderToolbar()
    const trigger = screen.getByRole('button', { name: /更多操作/ })
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
    fireEvent.click(trigger)

    const item = await screen.findByText('恢复初始分段')
    fireEvent.click(item)
    expect(props.onResetSegments).toHaveBeenCalled()
    unmount()
  })
})

describe('ReaderToolbar：inline 分支', () => {
  it('inline 时容器带 hidden min-[1100px]:flex（不自带独立行高度）', () => {
    const { container, unmount } = renderToolbar({ inline: true })
    const root = container.firstElementChild as HTMLElement
    expect(root.className).toContain('min-[1100px]:flex')
    unmount()
  })

  it('非 inline 时渲染为独立一行（带边框与响应式断点）', () => {
    const { container, unmount } = renderToolbar({ inline: false })
    const root = container.firstElementChild as HTMLElement
    // 独立行带 border-b；inline 版是 min-[1100px]:flex 的纯按钮组
    expect(root.className).toContain('border-b')
    expect(root.className).not.toContain('min-[1100px]:flex')
    unmount()
  })

  it('inline 时按钮组仍然完整', () => {
    const { container, unmount } = renderToolbar({ inline: true })
    expect(within(container).getByRole('button', { name: '选页' })).toBeTruthy()
    expect(within(container).getByRole('button', { name: /追加材料/ })).toBeTruthy()
    unmount()
  })
})
