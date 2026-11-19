// @vitest-environment jsdom
/**
 * AssistantPage（AI 助手独立页）渲染单测（jsdom）。
 *
 * 本页是布局外壳：会话装配在 useActiveSession（与抽屉共用，行为由 CopilotPanel
 * 的用例锁），流式收发归 store。所以这里只断言页面自己负责的语义：
 *  · 全宽：不搬抽屉的宽度约束（--copilot-w / max-w-[600px]），对话区照常挂载
 *  · 会话列表：宽屏常驻可折叠（偏好与抽屉共用 `copilot:rail`），窄屏收成覆盖层
 *  · 业务范围：合同范围的材料目录开关、退出范围回调
 *  · 输入区按当前后端能力决定是否提供插话；页面上没有「收起」（不是抽屉）
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  context: null as { origin: 'case' | 'contract'; refId: number; title: string } | null,
  draggingFiles: false,
  switchSession: vi.fn(async () => {}),
  exitContext: vi.fn(async () => {}),
  // CopilotHeader 里的 AgentBackendPicker 读这三项（空清单 = 退化为纯展示）
  backends: [] as Array<{ kind: string; label: string; description: string; available: boolean; reason: string; capabilities: Record<string, boolean> }>,
  selectedAgentKind: '',
  selectAgentKind: vi.fn(),
}))

const sessionMock = vi.hoisted(() => ({
  currentTitle: '',
  currentModel: '',
  currentAgentKind: null as string | null,
  currentCapabilities: {} as Record<string, boolean>,
}))
const mediaMock = vi.hoisted(() => ({ useMediaQuery: vi.fn(() => false) }))

vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('../hooks/use-active-session', () => ({ useActiveSession: () => sessionMock }))
vi.mock('@/hooks/use-media', () => mediaMock)
vi.mock('../hooks/use-copilot-drop', () => ({
  useCopilotDrop: () => ({
    onDragEnter: vi.fn(),
    onDragOver: vi.fn(),
    onDragLeave: vi.fn(),
    onDrop: vi.fn(),
  }),
}))

// 子组件换成可探桩：本文件只测页面外壳的布局与接线
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
vi.mock('./Composer', () => ({
  Composer: ({ steerEnabled }: { steerEnabled: boolean }) => (
    <div data-testid="composer">{String(steerEnabled)}</div>
  ),
}))
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

import { MemoryRouter, Route, Routes } from 'react-router'

import { AssistantPage } from './AssistantPage'

/**
 * 页面用 `useNavigate` / `useLocation`（它是路由组件，这是正当用法），所以渲染
 * 必须包一层 Router。不包的话测的是「组件在非法上下文里崩没崩」，不是它的行为。
 */
function renderPage(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mediaMock.useMediaQuery.mockReturnValue(false)
  storeMock.context = null
  storeMock.draggingFiles = false
  sessionMock.currentTitle = ''
  sessionMock.currentModel = ''
  sessionMock.currentAgentKind = null
  sessionMock.currentCapabilities = {}
})

describe('AssistantPage：全宽布局', () => {
  it('对话区照常挂载，页面不搬抽屉的宽度约束', () => {
    const { container } = renderPage()
    expect(screen.getByTestId('message-list')).toBeTruthy()
    expect(screen.getByTestId('composer')).toBeTruthy()

    // 宽度交给屏幕：抽屉的 --copilot-w（可拖宽的固定面板宽）与 max-w 约束都不该出现，
    // 否则多 agent 并排时每栏又被压回抽屉那档宽度
    const main = container.querySelector('main')!
    expect(main.className).toContain('w-full')
    expect(main.className).not.toContain('--copilot-w')
    expect(main.className).not.toContain('max-w')
    // 抽屉是 fixed 浮层（aside）；页面在文档流里，不该有它
    expect(container.querySelector('aside')).toBeNull()
  })

  it('标题取当前会话标题（空串回落「AI 助手」）', () => {
    const { unmount } = renderPage()
    expect(screen.getByText('AI 助手')).toBeTruthy()
    unmount()

    sessionMock.currentTitle = '合同违约分析'
    renderPage()
    expect(screen.getByText('合同违约分析')).toBeTruthy()
  })

  it('拖拽文件悬停时显示「松手添加附件」（与抽屉同一提示层）', () => {
    storeMock.draggingFiles = true
    renderPage()
    expect(screen.getByText('松手添加附件')).toBeTruthy()
  })
})

describe('AssistantPage：会话列表', () => {
  it('宽屏：常驻会话栏，开关落 localStorage（与抽屉同一个 key）', () => {
    mediaMock.useMediaQuery.mockReturnValue(true)
    renderPage()
    expect(screen.getByTestId('sidebar-rail')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '收起会话栏' }))
    expect(screen.queryByTestId('sidebar-rail')).toBeNull()
    expect(localStorage.getItem('copilot:rail')).toBe('0')

    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-rail')).toBeTruthy()
    expect(localStorage.getItem('copilot:rail')).toBe('1')
  })

  it('上次在抽屉里收起过（copilot:rail=0）时初始不显示会话栏', () => {
    mediaMock.useMediaQuery.mockReturnValue(true)
    localStorage.setItem('copilot:rail', '0')
    renderPage()
    expect(screen.queryByTestId('sidebar-rail')).toBeNull()
  })

  it('窄屏：列表收成覆盖层、可主动关闭，且这是瞬态开关（不写持久化）', () => {
    renderPage()
    expect(screen.queryByTestId('sidebar-rail')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-overlay')).toBeTruthy()
    expect(localStorage.getItem('copilot:rail')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '关闭列表' }))
    expect(screen.queryByTestId('sidebar-overlay')).toBeNull()
  })

  it('「新对话」清空会话并收起覆盖式列表', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '展开会话列表' }))
    expect(screen.getByTestId('sidebar-overlay')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /新对话/ }))
    expect(screen.queryByTestId('sidebar-overlay')).toBeNull()
    await waitFor(() => expect(storeMock.switchSession).toHaveBeenCalledWith(null))
  })
})

describe('AssistantPage：业务范围与输入区', () => {
  it('合同范围：材料目录可开可关；退出范围调 exitContext', async () => {
    storeMock.context = { origin: 'contract', refId: 88, title: '某某委托' }
    renderPage()
    expect(screen.getByText('AI 助手 · 某某委托')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '展开合同材料目录' }))
    expect(screen.getByTestId('tree-drawer').textContent).toContain('88')
    fireEvent.click(screen.getByRole('button', { name: '关闭目录' }))
    expect(screen.queryByTestId('tree-drawer')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '退出业务范围，回到全部会话' }))
    await waitFor(() => expect(storeMock.exitContext).toHaveBeenCalled())
  })

  it('输入区按后端能力决定是否提供插话（steer=false 时不该出现插话入口）', () => {
    sessionMock.currentCapabilities = { steer: false }
    renderPage()
    expect(screen.getByTestId('composer').textContent).toBe('false')
  })

  it('页面上没有「收起 AI 助手」：独立页不是抽屉，没有收起语义', () => {
    renderPage()
    expect(screen.queryByRole('button', { name: '收起 AI 助手' })).toBeNull()
  })
})

describe('AssistantPage：退出全屏', () => {
  // 真实反馈：全屏之后不知道怎么缩回去。全屏页没有导航入口可以「点回去」，
  // 所以必须有明确的退出口——而且要是**带文字**的按钮，上一版只给图标没人找到。
  it('头部有可见的「退出全屏」按钮', () => {
    renderPage()
    expect(screen.getByRole('button', { name: '退出全屏' })).toBeTruthy()
    expect(screen.getByText('退出全屏')).toBeTruthy()
  })

  it('站内进入（有历史栈）时退回上一页，而不是弹回首页', () => {
    // 造出「从 /projects 点进来」的历史：location.key 不是 'default'
    render(
      <MemoryRouter initialEntries={['/projects', '/assistant']} initialIndex={1}>
        <Routes>
          <Route path="/projects" element={<div>项目页标记</div>} />
          <Route path="/" element={<div>首页标记</div>} />
          <Route path="/assistant" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: '退出全屏' }))

    // 回到进入前那一页
    expect(screen.getByText('项目页标记')).toBeTruthy()
    expect(screen.queryByText('首页标记')).toBeNull()
  })

  it('直接打开页面（无站内历史）时退到首页，不把用户弹出应用', () => {
    // `/assistant` 作为唯一入口 → location.key === 'default'，此时 navigate(-1)
    // 会离开应用（浏览器空白页），所以必须回落首页。
    render(
      <MemoryRouter initialEntries={['/assistant']}>
        <Routes>
          <Route path="/" element={<div>首页标记</div>} />
          <Route path="/assistant" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: '退出全屏' }))

    expect(screen.getByText('首页标记')).toBeTruthy()
  })
})
