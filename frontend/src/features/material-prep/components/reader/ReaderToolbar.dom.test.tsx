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
    maxCols: 3,
    onSetCols: vi.fn(),
    colsDisabled: false,
    onResetSegments: vi.fn(),
    onAutoSplit: vi.fn(),
    autoSplitRunning: false,
    autoSplitProgress: '',
    layoutMode: 'fast_text' as const,
    onLayoutModeChange: vi.fn(),
    cloudBackend: 'auto' as const,
    onCloudBackendChange: vi.fn(),
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

  it('常驻区只有一个视图入口，显示当前倍率', () => {
    const { unmount } = renderToolbar({ zoomVal: 150, cols: 2 })
    const btn = screen.getByRole('button', { name: /视图设置：当前 150%，2 列/ })
    expect(btn.textContent).toContain('150%')
    // 旧的 −/100%/+ 常驻三件套已收进菜单，不应再出现在常驻区
    expect(screen.queryByRole('button', { name: '缩小画布' })).toBeNull()
    expect(screen.queryByRole('button', { name: '放大画布' })).toBeNull()
    unmount()
  })
})

describe('ReaderToolbar：视图菜单（缩放 + 并排列数）', () => {
  // Radix 下拉由 pointerDown 打开（不是 click），且打开后触发按钮的
  // aria-haspopup/aria-expanded 会变，所以先抓元素再点。
  async function openViewMenu(over: Partial<ToolbarProps> = {}) {
    const utils = renderToolbar(over)
    const trigger = screen.getByRole('button', { name: /视图设置/ })
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' })
    const menu = await screen.findByRole('menu')
    return Object.assign(utils, { menu })
  }

  it('− / + 回调缩放', async () => {
    const { props, menu, unmount } = await openViewMenu()
    fireEvent.click(within(menu).getByRole('button', { name: '缩小画布' }))
    fireEvent.click(within(menu).getByRole('button', { name: '放大画布' }))
    expect(props.onZoomOut).toHaveBeenCalled()
    expect(props.onZoomIn).toHaveBeenCalled()
    unmount()
  })

  it('重置是明确的菜单项，而非伪装成百分比的按钮', async () => {
    const { props, menu, unmount } = await openViewMenu({ zoomVal: 150 })
    fireEvent.click(within(menu).getByRole('menuitem', { name: /恢复到 100%/ }))
    expect(props.onZoomReset).toHaveBeenCalled()
    unmount()
  })

  it('已在 100% 时重置项禁用', async () => {
    const { menu, unmount } = await openViewMenu({ zoomVal: 100 })
    const item = within(menu).getByRole('menuitem', { name: /恢复到 100%/ })
    expect(item.getAttribute('aria-disabled')).toBe('true')
    unmount()
  })

  it('达到上下限时 − / + 禁用', async () => {
    const { menu, unmount } = await openViewMenu({ zoomVal: 220 })
    const plus = within(menu).getByRole('button', { name: '放大画布' }) as HTMLButtonElement
    expect(plus.disabled).toBe(true)
    unmount()
  })

  it('列数按窗口上限逐项列出，点哪列就是哪列（不循环）', async () => {
    const { props, menu, unmount } = await openViewMenu({ cols: 1, maxCols: 3 })
    expect(within(menu).getByRole('menuitem', { name: /单页/ })).toBeTruthy()
    expect(within(menu).getByRole('menuitem', { name: /2 列/ })).toBeTruthy()
    expect(within(menu).getByRole('menuitem', { name: /3 列/ })).toBeTruthy()
    fireEvent.click(within(menu).getByRole('menuitem', { name: /3 列/ }))
    expect(props.onSetCols).toHaveBeenCalledWith(3)
    unmount()
  })

  it('窗口只够一列时只列「单页」并提示原因', async () => {
    const { menu, unmount } = await openViewMenu({ cols: 1, maxCols: 1, colsDisabled: true })
    expect(within(menu).getByRole('menuitem', { name: /单页/ })).toBeTruthy()
    expect(within(menu).queryByRole('menuitem', { name: /2 列/ })).toBeNull()
    expect(within(menu).getByText(/并排至少每列 360px/)).toBeTruthy()
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

describe('ReaderToolbar：自动分段 split button', () => {
  /** 打开右侧小三角的设置菜单 */
  async function openSettings() {
    const trigger = screen.getByRole('button', { name: /自动分段设置/ })
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false })
    fireEvent.click(trigger)
    await screen.findByText(/版面策略/)
  }

  it('主按钮直接执行自动分段（不需要先开菜单）', () => {
    const { props, unmount } = renderToolbar()
    // 精确匹配主按钮（另有「自动分段设置」按钮，模糊匹配会命中两个）
    fireEvent.click(screen.getByRole('button', { name: '自动分段' }))
    expect(props.onAutoSplit).toHaveBeenCalled()
    unmount()
  })

  it('设置菜单里能切版面策略到「补版面」', async () => {
    const { props, unmount } = renderToolbar()
    await openSettings()
    fireEvent.click(screen.getByText('补版面'))
    expect(props.onLayoutModeChange).toHaveBeenCalledWith('layout')
    unmount()
  })

  it('设置菜单里能选解析平台', async () => {
    const { props, unmount } = renderToolbar()
    await openSettings()
    fireEvent.click(screen.getByText('仅 Textin'))
    expect(props.onCloudBackendChange).toHaveBeenCalledWith('textin')
    unmount()
  })

  it('设置菜单里能触发「恢复初始分段」', async () => {
    const { props, unmount } = renderToolbar()
    await openSettings()
    fireEvent.click(screen.getByText('恢复初始分段'))
    expect(props.onResetSegments).toHaveBeenCalled()
    unmount()
  })

  it('当前值带 ✓，且每个选项都写明后果（费用/可信度）', async () => {
    const { unmount } = renderToolbar({ layoutMode: 'layout', cloudBackend: 'mineru' })
    await openSettings()

    // 勾选只出现在当前值上
    const layoutItem = screen.getByText('补版面').closest('[role="menuitem"]') as HTMLElement
    expect(layoutItem.querySelector('svg')).toBeTruthy()
    const textItem = screen.getByText('仅文本层').closest('[role="menuitem"]') as HTMLElement
    expect(textItem.querySelector('svg')).toBeNull()

    // 后果文案必须在：这几个选项直接影响计费与结果可信度，
    // 只写名词用户无从判断
    expect(screen.getByText(/按页计费/)).toBeTruthy()
    // 「失败不降级」两个锁定项都有，用 getAllBy 断言至少出现
    expect(screen.getAllByText(/失败不降级/).length).toBeGreaterThan(0)
    unmount()
  })

  it('识别进行中时主按钮与设置入口都禁用（避免改到正在跑的策略）', () => {
    const { unmount } = renderToolbar({ autoSplitRunning: true })
    expect((screen.getByRole('button', { name: /识别/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: /自动分段设置/ }) as HTMLButtonElement).disabled).toBe(true)
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
