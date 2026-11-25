// @vitest-environment jsdom
/**
 * ReaderToolbar 测试（jsdom）。
 *
 * 阅读器工具组，两条分支维度：
 * - narrow（<1100px）多出「材料 / 信息」两个抽屉开关；非 narrow 不渲染它们
 * - inline（嵌入顶栏）只输出按钮组；非 inline 自带容器
 *
 * 各按钮的 on/off 态、禁用态、自动分段的忙碌文案，以及「恢复初始分段」
 * 收在 ⋯ 菜单里防误触。末尾另有 ReaderBody 的进度面板接线用例（见文件内说明）。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReaderBody } from './ReaderBody'
import { ReaderToolbar } from './ReaderToolbar'
import type { CloudSelection } from './platform-selection'

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
    cloudSelection: [] as CloudSelection,
    onToggleCloudEngine: vi.fn(),
    onClearCrossCheck: vi.fn(),
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

  it('运行中禁用，按钮只留固定短文案（详细进度在底部面板）', () => {
    // 按钮以前会把「正在识别 84/164 页（51%）」整句塞进 name，手机构成工具条
    // （46px 固定高度、横向滚动）会被撑爆。现在进度归底部面板，按钮固定「识别中…」，
    // 当前页仍挂在 title 上供鼠标悬停查看。
    const { unmount } = renderToolbar({ autoSplitRunning: true, autoSplitProgress: '识别 3/10' })
    const btn = screen.getByRole('button', { name: /识别中…/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toContain('识别 3/10')
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

  it('设置菜单里能勾一个引擎（锁定该引擎）', async () => {
    const { props, unmount } = renderToolbar()
    await openSettings()
    fireEvent.click(screen.getByText('Textin'))
    expect(props.onToggleCloudEngine).toHaveBeenCalledWith('textin')
    unmount()
  })

  it('解析平台是多选：三个引擎都能勾，且 PaddleOCR-VL 在列', async () => {
    const { unmount } = renderToolbar()
    await openSettings()
    for (const name of ['MinerU', 'PaddleOCR-VL', 'Textin']) {
      expect(screen.getByRole('menuitemcheckbox', { name: new RegExp(name) })).toBeTruthy()
    }
    unmount()
  })

  it('不勾任何引擎时说明「= 自动容灾」，且不出现比对提示', async () => {
    const { unmount } = renderToolbar({ cloudSelection: [] })
    await openSettings()
    expect(screen.getByText(/不勾任何引擎 = 自动容灾/)).toBeTruthy()
    expect(screen.queryByText(/将交叉比对/)).toBeNull()
    unmount()
  })

  it('勾一个时不比对，提示是「锁定」', async () => {
    const { unmount } = renderToolbar({ cloudSelection: ['mineru'] })
    await openSettings()
    expect(screen.getByText(/只勾一个 = 锁定该引擎/)).toBeTruthy()
    expect(screen.queryByText(/将交叉比对/)).toBeNull()
    unmount()
  })

  it('勾两个及以上时出现「将交叉比对」提示与已选数量', async () => {
    const { unmount } = renderToolbar({ cloudSelection: ['mineru', 'paddleocr_vl'] })
    await openSettings()
    expect(screen.getByText(/已选 2 个引擎 → 将交叉比对/)).toBeTruthy()
    unmount()
  })

  it('勾选状态落在 aria-checked 上（勾了两个引擎 → 两项 checked）', async () => {
    const { unmount } = renderToolbar({ cloudSelection: ['mineru', 'paddleocr_vl'] })
    await openSettings()
    expect(screen.getByRole('menuitemcheckbox', { name: /MinerU/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('menuitemcheckbox', { name: /PaddleOCR-VL/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('menuitemcheckbox', { name: /Textin/ }).getAttribute('aria-checked')).toBe('false')
    unmount()
  })

  it('多选菜单勾一下不会收起菜单（否则勾第二个要重新打开）', async () => {
    const { unmount } = renderToolbar()
    await openSettings()
    fireEvent.click(screen.getByText('MinerU'))
    // Radix 默认选中即关闭；多选项必须在 onSelect 里 preventDefault
    expect(screen.queryByRole('menu')).toBeTruthy()
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
    const { unmount } = renderToolbar({ layoutMode: 'layout', cloudSelection: ['mineru'] })
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

  /**
   * P3-1 / P3-3：这两组选择直接决定本包的云端费用，且**按包持久化**。
   * 新建包默认开双引擎，所以「关掉」必须一步可达，计费后果必须写在选项上。
   */
  it('勾了两个引擎时给一键关闭交叉比对的入口，点了回调', async () => {
    const { props, unmount } = renderToolbar({ cloudSelection: ['mineru', 'paddleocr_vl'] })
    await openSettings()
    fireEvent.click(screen.getByText('关闭交叉比对（回到自动容灾）'))
    expect(props.onClearCrossCheck).toHaveBeenCalled()
    unmount()
  })

  it('没在比对时不渲染关闭入口（不制造无意义选项）', async () => {
    const { unmount } = renderToolbar({ cloudSelection: ['mineru'] })
    await openSettings()
    expect(screen.queryByText(/关闭交叉比对/)).toBeNull()
    unmount()
  })

  it('两组选择都标注「本包记住」，补版面写明更慢更贵', async () => {
    const { unmount } = renderToolbar()
    await openSettings()
    expect(screen.getAllByText(/本包记住/)).toHaveLength(2)
    expect(screen.getByText(/电子页也送云端：更准但更慢更贵/)).toBeTruthy()
    unmount()
  })

  it('比对态说明「换来错字清单 + 可一键关闭」，让默认开启的计费有对价说明', async () => {
    const { unmount } = renderToolbar({ cloudSelection: ['mineru', 'paddleocr_vl'] })
    await openSettings()
    expect(screen.getByText(/换来的是「两个引擎读得不一样」的错字清单/)).toBeTruthy()
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

/**
 * 进度面板接线（挂在 ReaderBody 的 SelectionBar 旁）。
 *
 * 这里只守「有没有挂上去、任务态有没有流到面板」：面板自己的阶段文案 / 进度映射 /
 * 耗时格式由 AutoSplitProgress.dom.test 覆盖。之所以要用真实 ReaderBody 而不是
 * 单独测面板——这条 props 链路（use-reader-screen → bodyProps → ReaderBody）是
 * 新增的，断在中间就没人发现面板永远不会出现。
 */
describe('ReaderBody：自动分段进度面板接线', () => {
  const draft = {
    mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 2 }],
    segs: [{ id: 's1', t: 'other', fn: '第一份', refs: [{ mi: 0, p: 0 }], manual: false }],
    infos: [],
    engineDisagreements: [],
    engineChecked: [],
  } as never

  function renderBody(over: Record<string, unknown> = {}) {
    return render(
      <ReaderBody
        draft={draft}
        messageId={1}
        narrow={false}
        railOpen={false}
        metaOpen={false}
        onOpenMeta={vi.fn()}
        onRotatePages={vi.fn()}
        onResetAllRotation={vi.fn()}
        onCollapsePanels={vi.fn()}
        railWrapCls=""
        metaWrapCls=""
        pickInfo={-1}
        pickField=""
        selMode={false}
        selPages={[]}
        selCount={0}
        selCross={false}
        focusedSeg={0}
        zoom={1}
        effCols={1}
        ocrPending={null}
        flowOps={{ pickPage: vi.fn(), setValue: vi.fn() } as never}
        metaOps={{} as never}
        onToggleSel={vi.fn()}
        onOcrBox={vi.fn() as never}
        onRequestDelete={vi.fn()}
        onFocusSeg={vi.fn()}
        onRenameMat={vi.fn()}
        onSetPickInfo={vi.fn()}
        onClearSel={vi.fn()}
        onApplySel={vi.fn()}
        onExitHint={vi.fn()}
        flowWrapRef={vi.fn()}
        onToggleEngineChecked={vi.fn()}
        {...over}
      />,
    )
  }

  it('没有在跑的任务时不渲染进度面板', () => {
    const { container } = renderBody()
    expect(screen.queryByTestId('auto-split-progress')).toBeNull()
    container.remove()
  })

  it('有任务时渲染面板并显示当前阶段', () => {
    const { container } = renderBody({
      autoSplitTask: {
        jobId: 'job-1',
        owned: false,
        snapshot: {
          jobId: 'job-1',
          status: 'processing',
          stage: 'cross_check',
          progressPct: 100,
          processedPages: 164,
          totalPages: 164,
          elapsedSeconds: 400,
          staleSeconds: 3,
          errorMessage: '',
          dualEngines: 'mineru,paddleocr_vl',
          sourceName: '证据材料.pdf',
        },
      },
      onHideAutoSplit: vi.fn(),
    })
    expect(screen.getByTestId('auto-split-progress')).toBeTruthy()
    expect(screen.getByText(/双引擎交叉比对中/)).toBeTruthy()
    expect(screen.getByText('已用 6 分 40 秒')).toBeTruthy()
    container.remove()
  })

  it('刚提交、还没有快照时也显示面板（提交 164 页要几十秒）', () => {
    const { container } = renderBody({ autoSplitTask: { jobId: 'job-2', owned: true, snapshot: null } })
    expect(screen.getByTestId('auto-split-progress')).toBeTruthy()
    expect(screen.getByText('正在识别文字')).toBeTruthy()
    container.remove()
  })
})
