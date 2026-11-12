// @vitest-environment jsdom
/**
 * CopilotPanel 外壳单测（jsdom）。
 *
 * 面板本体是布局外壳，价值集中在**头部状态与开关**上，故子组件（会话栏 / 消息区 /
 * 输入区 / 目录树）全部替换成可探桩，断言只落在面板自己负责的语义：
 *  · 标题优先级：业务范围（context）> 当前会话标题 > 「AI 助手」
 *  · 会话栏切换：宽屏走持久化开关（localStorage `copilot:rail`），窄屏走覆盖式列表
 *  · 业务范围 chip（本案/本委托）、合同范围的「材料」抽屉开关、并排模式按钮
 *  · 外部入口：待处理启动上下文（takePendingLaunchContext）与后续 COPILOT_LAUNCH_EVENT
 *  · 生命周期副作用：挂载恢复会话、流结束刷新历史/失效会话列表缓存、任务会话
 *    updated_at 变化后重拉转录
 *  · 滚轮囚闭：面板内无人能消费的 wheel 被 preventDefault，内部可滚动容器放行
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  sessionId: null as string | null,
  streaming: false,
  context: null as { origin: 'case' | 'contract'; refId: number; title: string } | null,
  draggingFiles: false,
  switchSession: vi.fn(async () => {}),
  enterContext: vi.fn(async () => {}),
  exitContext: vi.fn(async () => {}),
  loadPendingApprovals: vi.fn(async () => {}),
  refreshHistory: vi.fn(async () => {}),
}))

const apiMock = vi.hoisted(() => ({ listSessions: vi.fn() }))
const launchMock = vi.hoisted(() => ({ takePendingLaunchContext: vi.fn() }))
const mediaMock = vi.hoisted(() => ({ useMediaQuery: vi.fn(() => false) }))
const resizeMock = vi.hoisted(() => ({
  width: 600,
  railCapable: false,
  setPanelRef: vi.fn(),
  onHandlePointerDown: vi.fn(),
}))

vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('../api', () => apiMock)
vi.mock('../launch', () => ({
  COPILOT_LAUNCH_EVENT: 'copilot:launch',
  takePendingLaunchContext: launchMock.takePendingLaunchContext,
}))
vi.mock('@/hooks/use-media', () => mediaMock)
vi.mock('../hooks/use-panel-resize', () => ({ usePanelResize: () => resizeMock }))
vi.mock('../hooks/use-copilot-drop', () => ({
  useCopilotDrop: () => ({
    onDragEnter: vi.fn(),
    onDragOver: vi.fn(),
    onDragLeave: vi.fn(),
    onDrop: vi.fn(),
  }),
}))

// 子组件替换为可探桩：本用例只测面板外壳
vi.mock('./SessionSidebar', () => ({
  SessionSidebar: ({ variant, onClose }: { variant: string; onClose?: () => void }) => (
    <div data-testid={`sidebar-${variant}`}>
      <button type="button" onClick={onClose}>
        关闭列表
      </button>
    </div>
  ),
}))
vi.mock('./MessageList', () => ({ MessageList: () => <div data-testid="message-list" /> }))
vi.mock('./Composer', () => ({ Composer: () => <div data-testid="composer" /> }))
vi.mock('./FolderTreeDrawer', () => ({
  FolderTreeDrawer: ({ contractId, onClose }: { contractId: number; onClose: () => void }) => (
    <div data-testid="tree-drawer">
      目录 {contractId}
      <button type="button" onClick={onClose}>
        关闭目录
      </button>
    </div>
  ),
}))

import { CopilotPanel } from './CopilotPanel'

function session(over: Record<string, unknown> = {}) {
  return {
    session_id: 's-1',
    title: '',
    status: 'active',
    llm_model: '',
    origin: 'chat',
    created_at: '2026-10-20T10:00:00',
    updated_at: '2026-10-20T10:00:00',
    ...over,
  }
}

let queryClient: QueryClient

function renderPanel(props: Partial<React.ComponentProps<typeof CopilotPanel>> = {}) {
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return render(<CopilotPanel open onClose={vi.fn()} {...props} />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  storeMock.sessionId = null
  storeMock.streaming = false
  storeMock.context = null
  storeMock.draggingFiles = false
  mediaMock.useMediaQuery.mockReturnValue(false)
  resizeMock.railCapable = false
  launchMock.takePendingLaunchContext.mockReturnValue(null)
  apiMock.listSessions.mockResolvedValue([])
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(() => {
  queryClient.clear()
})

describe('CopilotPanel：标题与头部', () => {
  it('无会话无业务范围时标题为「AI 助手」，并发起一次挂载恢复会话', async () => {
    renderPanel()
    expect(screen.getByText('AI 助手')).toBeTruthy()
    // 挂载即恢复上次会话（StrictMode 双挂载幂等由 store 保证）
    await waitFor(() => expect(storeMock.switchSession).toHaveBeenCalledWith(null))
  })

  it('取会话列表缓存里的标题与模型展示；无会话时不显示模型徽标', async () => {
    storeMock.sessionId = 's-1'
    apiMock.listSessions.mockResolvedValue([session({ title: '合同违约分析', llm_model: 'claude-x' })])
    renderPanel()
    await waitFor(() => expect(screen.getByText('合同违约分析')).toBeTruthy())
    expect(apiMock.listSessions).toHaveBeenCalledWith(50, undefined)
    expect(screen.getByText('claude-x')).toBeTruthy()
  })

  it('业务范围优先于会话标题，并显示「本案」chip；点击 chip 退出范围', async () => {
    storeMock.sessionId = 's-1'
    storeMock.context = { origin: 'case', refId: 390, title: '某某公司执行异议之诉' }
    apiMock.listSessions.mockResolvedValue([session({ title: '不该出现的标题' })])
    renderPanel()

    expect(screen.getByText('AI 助手 · 某某公司执行异议之诉')).toBeTruthy()
    expect(screen.queryByText('不该出现的标题')).toBeNull()
    // 会话列表按业务范围取，不与全量列表共用缓存
    expect(apiMock.listSessions).toHaveBeenCalledWith(50, { origin: 'case', refId: 390 })

    fireEvent.click(screen.getByRole('button', { name: '退出业务范围，回到全部会话' }))
    expect(screen.getByRole('button', { name: '退出业务范围，回到全部会话' }).textContent).toContain('本案')
    await waitFor(() => expect(storeMock.exitContext).toHaveBeenCalled())
  })

  it('合同范围显示「本委托」chip 与「材料」目录开关', async () => {
    storeMock.context = { origin: 'contract', refId: 88, title: '某某委托' }
    renderPanel()
    expect(screen.getByRole('button', { name: '退出业务范围，回到全部会话' }).textContent).toContain('本委托')

    const treeBtn = screen.getByRole('button', { name: '展开合同材料目录' })
    expect(treeBtn.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(treeBtn)
    expect(screen.getByTestId('tree-drawer').textContent).toContain('88')
    expect(screen.getByRole('button', { name: '收起合同材料目录' }).getAttribute('aria-pressed')).toBe(
      'true',
    )

    fireEvent.click(screen.getByRole('button', { name: '关闭目录' }))
    expect(screen.queryByTestId('tree-drawer')).toBeNull()
  })

  it('非合同范围不出现「材料」按钮', () => {
    storeMock.context = { origin: 'case', refId: 1, title: '某案' }
    renderPanel()
    expect(screen.queryByRole('button', { name: '展开合同材料目录' })).toBeNull()
  })

  it('「新对话」清空会话并收起覆盖式列表', async () => {
    storeMock.sessionId = 's-1'
    resizeMock.railCapable = false
    renderPanel()
    // 先打开覆盖式列表，再点新对话，列表应一并收起
    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-overlay')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /新对话/ }))
    expect(screen.queryByTestId('sidebar-overlay')).toBeNull()
    await waitFor(() => expect(storeMock.switchSession).toHaveBeenCalledWith(null))
  })

  it('「收起 AI 助手」调用 onClose', () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    fireEvent.click(screen.getByRole('button', { name: '收起 AI 助手' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('打开态挂 slide-in 动画、收起态挂 slide-out，面板挂在 aside 上', () => {
    const { container, rerender } = renderPanel({ open: true })
    const aside = container.querySelector('aside')!
    expect(aside.className).toContain('slide-in-from-right')
    rerender(<CopilotPanel open={false} onClose={vi.fn()} />)
    expect(container.querySelector('aside')!.className).toContain('slide-out-to-right')
  })
})

describe('CopilotPanel：会话栏切换', () => {
  it('宽屏（railCapable）：开关持久化到 localStorage', () => {
    resizeMock.railCapable = true
    renderPanel()
    // 默认常驻会话栏可见
    expect(screen.getByTestId('sidebar-rail')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '收起会话栏' }))
    expect(screen.queryByTestId('sidebar-rail')).toBeNull()
    expect(localStorage.getItem('copilot:rail')).toBe('0')

    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-rail')).toBeTruthy()
    expect(localStorage.getItem('copilot:rail')).toBe('1')
  })

  it('上次收起过（copilot:rail=0）时初始不显示常驻会话栏', () => {
    resizeMock.railCapable = true
    localStorage.setItem('copilot:rail', '0')
    renderPanel()
    expect(screen.queryByTestId('sidebar-rail')).toBeNull()
  })

  it('窄屏：切换出来的是覆盖式列表，可主动关闭', () => {
    renderPanel()
    expect(screen.queryByTestId('sidebar-overlay')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-overlay')).toBeTruthy()
    // 窄屏不写持久化（该开关是瞬态）
    expect(localStorage.getItem('copilot:rail')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '关闭列表' }))
    expect(screen.queryByTestId('sidebar-overlay')).toBeNull()
  })
})

describe('CopilotPanel：并排模式按钮', () => {
  it('dockCapable 时出现切换按钮，aria-pressed 反映当前模式，点击回调', () => {
    const onDockToggle = vi.fn()
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <CopilotPanel open onClose={vi.fn()} dockCapable docked={false} onDockToggle={onDockToggle} />
      </QueryClientProvider>,
    )
    const btn = screen.getByRole('button', { name: '切换为并排模式' })
    fireEvent.click(btn)
    expect(onDockToggle).toHaveBeenCalled()

    rerender(
      <QueryClientProvider client={queryClient}>
        <CopilotPanel open onClose={vi.fn()} dockCapable docked onDockToggle={onDockToggle} />
      </QueryClientProvider>,
    )
    expect(screen.getByRole('button', { name: '切换为悬浮模式' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('缺 onDockToggle 或 dockCapable=false 时不渲染该按钮', () => {
    renderPanel({ dockCapable: false })
    expect(screen.queryByRole('button', { name: '切换为并排模式' })).toBeNull()
  })
})

describe('CopilotPanel：外部启动入口', () => {
  it('挂载时消费待处理的启动上下文', async () => {
    const ctx = { origin: 'contract' as const, refId: 12, title: '某委托' }
    launchMock.takePendingLaunchContext.mockReturnValue(ctx)
    renderPanel()
    await waitFor(() => expect(storeMock.enterContext).toHaveBeenCalledWith(ctx))
  })

  it('挂载后监听 COPILOT_LAUNCH_EVENT 切换上下文，卸载后解绑', async () => {
    const { unmount } = renderPanel()
    const ctx = { origin: 'case' as const, refId: 7, title: '某案' }

    act(() => {
      window.dispatchEvent(new CustomEvent('copilot:launch', { detail: ctx }))
    })
    await waitFor(() => expect(storeMock.enterContext).toHaveBeenCalledWith(ctx))

    storeMock.enterContext.mockClear()
    unmount()
    act(() => {
      window.dispatchEvent(new CustomEvent('copilot:launch', { detail: ctx }))
    })
    expect(storeMock.enterContext).not.toHaveBeenCalled()
  })

  it('事件 detail 为 null 时不触发 enterContext', async () => {
    renderPanel()
    act(() => {
      window.dispatchEvent(new CustomEvent('copilot:launch', { detail: null }))
    })
    expect(storeMock.enterContext).not.toHaveBeenCalled()
  })
})

describe('CopilotPanel：生命周期副作用', () => {
  it('非流式时拉待审列表；流式中不拉', async () => {
    storeMock.streaming = true
    const { rerender } = renderPanel()
    expect(storeMock.loadPendingApprovals).not.toHaveBeenCalled()

    storeMock.streaming = false
    rerender(
      <QueryClientProvider client={queryClient}>
        <CopilotPanel open onClose={vi.fn()} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(storeMock.loadPendingApprovals).toHaveBeenCalled())
  })

  it('流结束后失效会话列表缓存（首条消息会自动生成标题）', async () => {
    storeMock.sessionId = 's-1'
    storeMock.streaming = true
    renderPanel()
    await waitFor(() => expect(apiMock.listSessions).toHaveBeenCalled())
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    // 流式结束 → 面板重跑该 effect → ['copilot','sessions'] 被打上失效标记，
    // 侧栏据此重取列表，让自动生成的首条标题浮上来
    storeMock.streaming = false
    fireEvent.click(screen.getByRole('button', { name: '收起 AI 助手' }))
    await waitFor(() =>
      expect(invalidate.mock.calls.map((c) => c[0])).toContainEqual({ queryKey: ['copilot', 'sessions'] }),
    )
  })

  it('任务会话 updated_at 变化后重拉转录（后台任务的产出不在流式路径里）', async () => {
    storeMock.sessionId = 's-1'
    apiMock.listSessions.mockResolvedValue([
      session({ origin: 'task', updated_at: '2026-10-20T10:00:00' }),
    ])
    renderPanel()
    await waitFor(() => expect(apiMock.listSessions).toHaveBeenCalled())
    // 第一次出现的 updated_at 只记录不刷新（挂载不是「任务跑完了」）
    await waitFor(() => expect(screen.getByText('AI 助手')).toBeTruthy())
    expect(storeMock.refreshHistory).not.toHaveBeenCalled()

    apiMock.listSessions.mockResolvedValue([
      session({ origin: 'task', updated_at: '2026-10-20T10:05:00' }),
    ])
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
    })
    await waitFor(() => expect(storeMock.refreshHistory).toHaveBeenCalled())
  })

  it('对话式会话的 updated_at 变化不重拉（store 已实时追加）', async () => {
    storeMock.sessionId = 's-1'
    apiMock.listSessions.mockResolvedValue([session({ origin: 'chat', updated_at: '2026-10-20T10:00:00' })])
    renderPanel()
    await waitFor(() => expect(apiMock.listSessions).toHaveBeenCalled())
    apiMock.listSessions.mockResolvedValue([session({ origin: 'chat', updated_at: '2026-10-20T10:05:00' })])
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
    })
    expect(storeMock.refreshHistory).not.toHaveBeenCalled()
  })

  it('拖拽文件悬停时显示「松手添加附件」提示层', () => {
    storeMock.draggingFiles = true
    renderPanel()
    expect(screen.getByText('松手添加附件')).toBeTruthy()
    expect(screen.getByText(/单个 ≤ 20MB/)).toBeTruthy()
  })
})

describe('CopilotPanel：滚轮囚闭', () => {
  it('面板内无人能消费的 wheel 被阻断（不带动下层页面）', () => {
    const { container } = renderPanel()
    const aside = container.querySelector('aside')!
    const event = new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true })
    aside.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('内部可滚动容器到边界之外时可消费，放行不阻断', () => {
    const { container } = renderPanel()
    const aside = container.querySelector('aside')!
    const scroller = document.createElement('div')
    scroller.style.overflowY = 'auto'
    // jsdom 不做布局：手工给出「内容超出」的度量
    Object.defineProperty(scroller, 'scrollHeight', { value: 500, configurable: true })
    Object.defineProperty(scroller, 'clientHeight', { value: 200, configurable: true })
    Object.defineProperty(scroller, 'scrollTop', { value: 0, configurable: true, writable: true })
    aside.appendChild(scroller)

    // 向下滚且未到底 → 由内部容器消费
    const down = new WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true })
    scroller.dispatchEvent(down)
    expect(down.defaultPrevented).toBe(false)

    // 滚到顶部后向上滚 → 内部消费不了（scrollTop 为 0），阻断
    const up = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true })
    scroller.dispatchEvent(up)
    expect(up.defaultPrevented).toBe(true)
  })

  it('ctrl+wheel（浏览器缩放）不接管', () => {
    const { container } = renderPanel()
    const event = new WheelEvent('wheel', { deltaY: 120, ctrlKey: true, bubbles: true, cancelable: true })
    container.querySelector('aside')!.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })

  it('已 defaultPrevented 的事件不再处理', () => {
    const { container } = renderPanel()
    const event = new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true })
    event.preventDefault()
    container.querySelector('aside')!.dispatchEvent(event)
    // 保持被阻断（不是被本组件二次处理的证据：preventDefault 只置一次 true）
    expect(event.defaultPrevented).toBe(true)
  })
})
