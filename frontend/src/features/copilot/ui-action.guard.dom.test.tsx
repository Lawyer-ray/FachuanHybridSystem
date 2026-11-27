// @vitest-environment jsdom
/**
 * 「AI 操作页面」的**失败与守护态**端到端集成（jsdom）：链路与
 * `ui-action.e2e.dom.test.tsx` 完全相同（只替身 HTTP 边界），这里只钉「出事时」的几面：
 *
 * - 执行失败必须**留得住**（横幅红态、不淡出）——落完就消失等于告诉律师「什么都没发生」；
 * - 前端不认识的动作（后端清单比前端新）必须**说出来**：运行记录 `unknown_action` +
 *   真的弹提示 + 页面不动。T1 是单向指令、结果不回传模型，静默失败就变成「AI 说已经帮你
 *   打开了，页面一动不动，日志里连一条错误都没有」；
 * - 宿主没挂载（面板与助手页都不在场）→ `executor_error`，不抛异常、不导航；
 * - 没有 Router 时横幅照常渲染、宿主静默不注入端口（不炸 `useNavigate`）。
 *
 * 为什么与主文件拆开：单文件 450 行硬红线；两组用例的时钟策略也不同（淡出要假计时器，
 * 提示要真计时器——sonner 的 `<Toaster/>` 得过一个宏任务才把 toast 挂进 DOM）。
 * api 的替身清单在两个文件里各写一遍是 vitest 的硬约束（`vi.mock` 按文件生效、工厂
 * 提升到文件顶部），不是重复代码。
 */

import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { Toaster } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { UiActionBanner } from './components/UiActionBanner'
import { UiToolHost } from './components/UiToolHost'
import type { UiToolRun } from './state-types'
import type { AgentSession } from './types'

/** 唯一替身：HTTP 边界。逐个列出导出（缺一个 → `x is not a function`），见主文件同处说明 */
vi.mock('./api', () => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  fetchBackends: vi.fn(),
  deleteSession: vi.fn(),
  renameSession: vi.fn(),
  fetchHistory: vi.fn(),
  decideApproval: vi.fn(),
  openRegenerateStream: vi.fn(),
  openMessageStream: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  getUsageSummary: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
  createFolderRef: vi.fn(),
  rateMessage: vi.fn(),
  answerQuestion: vi.fn(),
  fetchPendingQuestions: vi.fn(),
  cancelAgentTask: vi.fn(),
  fetchAgentSkills: vi.fn(),
  setAgentSkillEnabled: vi.fn(),
  fetchSessionStats: vi.fn(),
  compactSession: vi.fn(),
  fetchQoderAuth: vi.fn(),
  startQoderLogin: vi.fn(),
  fetchQoderLoginStatus: vi.fn(),
  fetchQoderByok: vi.fn(),
  registerQoderByok: vi.fn(),
  deleteQoderByok: vi.fn(),
  adoptReview: vi.fn(),
  fetchReview: vi.fn(),
  fetchReviewAdoption: vi.fn(),
  fetchReviewOptions: vi.fn(),
  fetchSynthesis: vi.fn(),
  REVIEW_TIMEOUT_MS: 180_000,
  runReview: vi.fn(),
  runSynthesis: vi.fn(),
  clearScopeFolderRowsCache: vi.fn(),
  fetchCaseFolderEntries: vi.fn(),
  fetchContractFolderEntries: vi.fn(),
  fetchScopeFolderEntries: vi.fn(),
  loadScopeFolderRows: vi.fn(),
  SCOPE_SUBDIR_SCAN: 6,
  globalSearch: vi.fn(),
  createProjectNote: vi.fn(),
}))

const encoder = new TextEncoder()

const SESSION: AgentSession = {
  session_id: 's-1',
  title: '',
  status: 'active',
  llm_model: '',
  agent_kind: 'pi',
  created_at: '',
  updated_at: '',
}

/** 一次性吐完所有帧：这几条用例都不需要观察流当中的状态 */
function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

const DONE_FRAME = 'data: {"type":"done","session_id":"s-1"}\n\n'

function actionFrame(callId: string, action: string, args: Record<string, unknown>): string {
  return `data: ${JSON.stringify({ type: 'ui_action', call_id: callId, action, arguments: args, route: null })}\n\n`
}

/** 地址探针：读真路由 location（`navigate` 被调用过 ≠ 地址变了） */
function LocationProbe() {
  const { pathname, search } = useLocation()
  return <div data-testid="loc">{`${pathname}${search}`}</div>
}

function renderCopilot(options: { withHost?: boolean; withToaster?: boolean } = {}) {
  const { withHost = true, withToaster = false } = options
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
      {/* 生产里由 AppShell 的面板 / 助手页挂载：布局与主文件一致（首页起步） */}
      {withHost && <UiToolHost />}
      <UiActionBanner />
      {withToaster && <Toaster />}
    </MemoryRouter>,
  )
}

/** 窄口径读运行记录：缺项时给出可读失败信息，而不是 undefined 引发的 TypeError */
function runOf(callId: string): UiToolRun {
  const run = useCopilot.getState().uiToolRuns[callId]
  if (!run) throw new Error(`缺少 callId=${callId} 的运行记录`)
  return run
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
  window.history.replaceState({}, '', '/')
  vi.mocked(copilotApi.createSession).mockResolvedValue(SESSION)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AI 操作页面：出事的时候律师看得见', () => {
  it('动作失败时横幅是红态且不淡出（失败必须留得住）', async () => {
    vi.useFakeTimers()
    // javascript: 不在站内白名单里 → route_unreachable（安全拦截，不重试同参数）
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([actionFrame('fail-1', 'ui_navigate', { path: 'javascript:alert(1)' }), DONE_FRAME]),
    )
    renderCopilot()

    await act(async () => {
      await useCopilot.getState().send('跳过去')
    })

    const banner = screen.getByTestId('ui-action-banner')
    expect(banner.textContent).toContain('AI 操作失败')
    // 红态（成功态是 border-border/bg-card，失败态是红系）
    expect(banner.className).toContain('bg-red-50')

    // 成功态 1.2 秒就淡出；失败态推进 5 秒后必须还在——律师要靠它知道「AI 想做但没做成」
    act(() => {
      vi.advanceTimersByTime(5_000)
    })
    expect(screen.getByTestId('ui-action-banner').textContent).toContain('AI 操作失败')
    expect(screen.getByTestId('ui-action-banner').className).toContain('bg-red-50')
  })

  it('后端清单比前端新（前端不认识的动作）→ 落 unknown_action、真的弹了提示、页面不动', async () => {
    // 真实计时器：sonner 的 <Toaster/> 要过一个宏任务才把 toast 挂进 DOM
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([actionFrame('unknown-1', 'ui_not_in_manifest', {}), DONE_FRAME]),
    )
    renderCopilot({ withToaster: true })

    await act(async () => {
      await useCopilot.getState().send('用一个前端还没有的动作')
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100))
    })

    // 版本漂移要被分类（打点告警的依据），不是笼统的「执行失败」
    expect(runOf('unknown-1')).toMatchObject({ name: 'ui_not_in_manifest', state: 'error', code: 'unknown_action' })
    // 页面一动不动
    expect(screen.getByTestId('loc').textContent).toBe('/')
    // 但律师看得见两处：横幅（红态）+ 提示（真的渲染进 DOM，不是被静默丢掉）
    expect(screen.getByTestId('ui-action-banner').textContent).toContain('AI 操作失败')
    expect(document.querySelector('[data-sonner-toast]')?.textContent).toContain('未知的界面动作')
  })

  it('宿主没挂载（面板与助手页都不在场）→ 落 executor_error，不抛异常也不导航', async () => {
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([actionFrame('nohost-1', 'ui_navigate', { path: '/projects' }), DONE_FRAME]),
    )
    // 不渲染 UiToolHost：等价于两处宿主都卸载（端口槽为空）
    renderCopilot({ withHost: false })

    await act(async () => {
      await useCopilot.getState().send('打开项目列表')
    })

    expect(screen.getByTestId('loc').textContent).toBe('/')
    expect(runOf('nohost-1')).toMatchObject({ state: 'error', code: 'executor_error' })
    // 连 toast 都发不出去（提示本身也是端口），但横幅读的是运行记录，仍然报失败——
    // 否则这条链路上唯一剩下的就是「什么都没发生」
    expect(screen.getByTestId('ui-action-banner').textContent).toContain('AI 操作失败')
  })

  it('没有 Router 时横幅照常渲染、宿主静默不注入端口（不炸 useNavigate）', () => {
    useCopilot.setState({
      uiToolRuns: { 'norouter-1': { name: 'ui_navigate', state: 'running', startedAt: Date.now() } },
    })

    // 面板自带「不依赖 router」的架构约束（CopilotPanel 的单测就不包 Router），
    // 所以 UiToolHost 用 useInRouterContext 守卫：无路由 = 正常态，渲染 null 而不是抛错
    const { container } = render(
      <>
        <UiToolHost />
        <UiActionBanner />
      </>,
    )

    // 宿主渲染 null：整棵子树只剩横幅这一个节点
    expect(container.children).toHaveLength(1)
    expect(screen.getByTestId('ui-action-banner').textContent).toContain('AI 正在操作')
  })
})
