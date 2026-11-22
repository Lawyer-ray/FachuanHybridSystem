// @vitest-environment jsdom
/**
 * useSessionRoute：会话 ↔ URL 双向同步（jsdom）。
 *
 * 「URL 能唯一定位一个会话」整套语义只有这一个实现处，所以这里按简报的行为表
 * 逐行钉死：直接打开带 id / 直接打开无 id（有、无上次会话）/ 侧栏切另一条 /
 * 新对话 / 删除后邻居接管 / 后退前进 / 坏 id。另加三条护栏：切会话必须是
 * `replace`（后退不能倒着回放刚才点过的会话）、同步不乒乓、刚发消息建出来的
 * 会话不能被当成坏 id。
 *
 * 用**真实 store**：同步的另一半就是 store 的 sessionId，把它 mock 掉等于自己
 * 跟自己演。只 mock 网络层（`../api`）与 toast。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listSessions: vi.fn(),
  fetchHistory: vi.fn(),
  fetchSessionStats: vi.fn(),
}))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn() }))

vi.mock('../api', () => apiMock)
vi.mock('sonner', () => ({ toast: toastMock }))

import type { AgentHistoryMessage, AgentSession, CopilotState } from '../types'
import { useCopilot } from '../store'
import { useSessionRoute } from './use-session-route'

/** store 的干净起点（每个用例都从「刷新后的空页」开始） */
const EMPTY_STORE: Partial<CopilotState> = {
  sessionId: null,
  messages: [],
  approvals: [],
  pendingQuestions: [],
  questionDrafts: {},
  streaming: false,
  sending: false,
  loadingHistory: false,
  lastError: null,
  noMoreHistory: false,
  queuePosition: null,
  queuedSteers: [],
  contextUsage: { used: null, total: null },
  context: null,
  compacting: false,
  selectedAgentKind: '',
  draggingFiles: false,
}

function sessionRow(id: string): AgentSession {
  return {
    session_id: id,
    title: id,
    status: 'active',
    llm_model: '',
    agent_kind: 'pi',
    created_at: '',
    updated_at: '',
  }
}

function historyRow(content: string): AgentHistoryMessage {
  return { message_id: 1, role: 'assistant', content, tool_name: '', created_at: '', metadata: {} }
}

/** 被测宿主：调用本 hook，并把当前 pathname 打在页面上（断言「URL 长什么样」） */
function PageHost() {
  useSessionRoute()
  const { pathname } = useLocation()
  return <div data-testid="pathname">{pathname}</div>
}

/** 浏览器后退/前进的驱动钮：MemoryRouter 不碰真实 history，只能从站内触发 */
function HistoryButtons() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => void navigate(-1)}>
        后退
      </button>
      <button type="button" onClick={() => void navigate(1)}>
        前进
      </button>
    </>
  )
}

function renderRoute(entries: string[], index = entries.length - 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries} initialIndex={index}>
        <HistoryButtons />
        <Routes>
          <Route path="/assistant" element={<PageHost />} />
          <Route path="/assistant/:sessionId" element={<PageHost />} />
          {/* 只用于验证「后退回到了进助手之前那一页」 */}
          <Route path="/projects" element={<div data-testid="pathname">/projects</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** 当前 URL（PathnameHost 打的 pathname） */
function currentPath(): string | null {
  return screen.getByTestId('pathname').textContent
}

/** 侧栏点会话 / 点「新对话」/ 删除后邻居接管，落到 store 上的都是这一句 */
async function pickSession(id: string | null) {
  await act(async () => {
    await useCopilot.getState().switchSession(id)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useCopilot.setState(EMPTY_STORE)
  apiMock.listSessions.mockResolvedValue([sessionRow('s-1'), sessionRow('s-2'), sessionRow('s-3')])
  apiMock.fetchHistory.mockImplementation((id: string) => Promise.resolve([historyRow(`来自 ${id} 的历史`)]))
  // 水位是增强信息（store 内部静默），这里让它失败即可
  apiMock.fetchSessionStats.mockRejectedValue(new Error('不关心'))
})

describe('行为表 1–3：首个 URL 决定打开哪个会话', () => {
  it('1. 直接打开 /assistant/<id>：打开该会话并拉历史', async () => {
    renderRoute(['/assistant/s-9'])

    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-9'))
    expect(apiMock.fetchHistory).toHaveBeenCalledWith('s-9')
    // 历史真的落进了转录（不是只把 id 换了一下）
    await waitFor(() =>
      expect(useCopilot.getState().messages.map((m) => m.content)).toContain('来自 s-9 的历史'),
    )
    // URL 没被 store 改写：贴过来的链接不能被换成自己上次那个会话
    expect(currentPath()).toBe('/assistant/s-9')
  })

  it('2. 直接打开 /assistant 且 localStorage 有上次会话：URL replace 成 /assistant/<id>，会话不变', async () => {
    // 刷新后 store 的 sessionId 由 localStorage 恢复，messages 还是空的
    useCopilot.setState({ sessionId: 's-0' })
    renderRoute(['/assistant'])

    await waitFor(() => expect(currentPath()).toBe('/assistant/s-0'))
    // 「刷新回到上次会话」的核心：会话没被换成新对话，也没被本 hook 重拉一遍
    expect(useCopilot.getState().sessionId).toBe('s-0')
    expect(apiMock.fetchHistory).not.toHaveBeenCalled()
  })

  it('3. 直接打开 /assistant 且无历史：新对话，URL 保持 /assistant', async () => {
    renderRoute(['/assistant'])
    await act(async () => {})

    expect(currentPath()).toBe('/assistant')
    expect(useCopilot.getState().sessionId).toBeNull()
    expect(apiMock.fetchHistory).not.toHaveBeenCalled()
  })
})

describe('行为表 4–6：store 变了，URL 跟上', () => {
  it('4. 侧栏点另一会话：切过去，URL replace 成新 id', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    renderRoute(['/assistant'])
    await waitFor(() => expect(currentPath()).toBe('/assistant/s-1'))

    await pickSession('s-2')

    await waitFor(() => expect(currentPath()).toBe('/assistant/s-2'))
    expect(useCopilot.getState().sessionId).toBe('s-2')
  })

  it('5. 点「新对话」：store 清空，URL replace 回 /assistant', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    renderRoute(['/assistant'])
    await waitFor(() => expect(currentPath()).toBe('/assistant/s-1'))

    await pickSession(null)

    await waitFor(() => expect(currentPath()).toBe('/assistant'))
    expect(useCopilot.getState().sessionId).toBeNull()
  })

  it('6. 删除当前会话（邻居顺位接管）：URL 跟随接管后的 id', async () => {
    // SessionSidebar 删除成功后调 switchSession(相邻会话 id)（先下后上），落到
    // store 上的就是这一句；URL 必须跟着邻居走，不能停在那条已删的 id 上。
    // 删当前会话的时刻，页面上早就打开着它（id 与 URL 一致，本 hook 不需要动它）
    useCopilot.setState({ sessionId: 's-2' })
    renderRoute(['/assistant/s-2'])
    await act(async () => {})

    await pickSession('s-3')

    await waitFor(() => expect(currentPath()).toBe('/assistant/s-3'))
    expect(apiMock.fetchHistory).toHaveBeenLastCalledWith('s-3')
  })
})

describe('行为表 7–8：URL 变了 / 坏 id', () => {
  it('7. 浏览器后退 / 前进：URL 变 → 会话跟随', async () => {
    renderRoute(['/assistant/s-1', '/assistant/s-2'])
    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-2'))

    fireEvent.click(screen.getByRole('button', { name: '后退' }))
    await waitFor(() => expect(currentPath()).toBe('/assistant/s-1'))
    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-1'))

    fireEvent.click(screen.getByRole('button', { name: '前进' }))
    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-2'))
  })

  it('8. /assistant/<不存在或已删>：不崩，列表加载完查无此 id 就退回 /assistant 并提示', async () => {
    apiMock.fetchHistory.mockRejectedValue(new Error('404 会话不存在'))
    renderRoute(['/assistant/ghost'])

    // 不崩：宿主一直在（store 会先停在坏 id 上，只留一句 lastError）
    await waitFor(() => expect(apiMock.listSessions).toHaveBeenCalled())
    expect(screen.getByTestId('pathname')).toBeTruthy()

    // 列表（s-1/s-2/s-3）里没有 ghost → 回新对话
    await waitFor(() => expect(currentPath()).toBe('/assistant'))
    await waitFor(() => expect(useCopilot.getState().sessionId).toBeNull())
    expect(toastMock.error).toHaveBeenCalledTimes(1)
    expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining('不存在'))
  })

  it('刷新恢复的会话已在别处被删：同样退回 /assistant（不只 URL 带来的 id 才兜底）', async () => {
    apiMock.fetchHistory.mockRejectedValue(new Error('404 会话不存在'))
    useCopilot.setState({ sessionId: 'gone-0' })
    renderRoute(['/assistant'])
    await waitFor(() => expect(currentPath()).toBe('/assistant/gone-0'))

    // 页面里这一步由 useActiveSession 挂载时完成；本 harness 只装了本 hook，手动来一次
    await pickSession('gone-0')

    await waitFor(() => expect(currentPath()).toBe('/assistant'))
    expect(useCopilot.getState().sessionId).toBeNull()
    expect(toastMock.error).toHaveBeenCalled()
  })
})

describe('防护：replace 语义 / 不乒乓 / 不误伤新会话', () => {
  it('切会话用 replace：后退回到进助手之前那一页，不倒退会话', async () => {
    renderRoute(['/projects', '/assistant/s-1'])
    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-1'))

    await pickSession('s-2')
    await waitFor(() => expect(currentPath()).toBe('/assistant/s-2'))

    fireEvent.click(screen.getByRole('button', { name: '后退' }))
    await waitFor(() => expect(currentPath()).toBe('/projects'))
  })

  it('双向同步不乒乓：一次切换只拉一次历史，URL 读回来不会反过来再切一遍 store', async () => {
    renderRoute(['/assistant/s-1'])
    await waitFor(() => expect(useCopilot.getState().sessionId).toBe('s-1'))

    await pickSession('s-2')
    await waitFor(() => expect(currentPath()).toBe('/assistant/s-2'))
    // 再放两拍：任何 store→URL→store 的来回都会在这里多留下一次 fetchHistory
    await act(async () => {})
    await act(async () => {})

    expect(apiMock.fetchHistory).toHaveBeenCalledTimes(2)
    expect(apiMock.fetchHistory).toHaveBeenNthCalledWith(1, 's-1')
    expect(apiMock.fetchHistory).toHaveBeenNthCalledWith(2, 's-2')
  })

  it('刚发消息建出来的会话不在列表里也不算坏 id（列表要等本轮流结束才刷新）', async () => {
    renderRoute(['/assistant'])
    await act(async () => {})

    // store/turn.ts 建会话成功后就 set({ sessionId })——此刻列表里还没有它
    await act(async () => {
      useCopilot.setState({ sessionId: 'new-1' })
    })
    await waitFor(() => expect(currentPath()).toBe('/assistant/new-1'))

    // 紧接着本轮报错（例如限流），列表仍是旧的（没有 new-1）
    await act(async () => {
      useCopilot.setState({ lastError: '当前使用人数较多，请稍后再试' })
    })
    await act(async () => {})

    expect(currentPath()).toBe('/assistant/new-1')
    expect(useCopilot.getState().sessionId).toBe('new-1')
    expect(toastMock.error).not.toHaveBeenCalled()
  })
})
