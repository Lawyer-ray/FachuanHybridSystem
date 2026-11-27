// @vitest-environment jsdom
/**
 * 「AI 操作页面」端到端集成（jsdom）：一帧 SSE 到律师眼前的那一下，全程真实现。
 *
 * 链路（除 HTTP 边界外**一个替身都没有**）：
 * ```
 * store.send                       store/turn-send.ts
 *  → openMessageStream             ← 唯一 mock：返回受控 ReadableStream（后端只当黑盒）
 *  → consumeAgentStream            streaming.ts（真 switch 分发）
 *  → onUiAction                    handlers/ui-action-handler.ts
 *  → runUiAction                   store/ui-tools.ts（幂等 / 打断 / 落态）
 *  → runUiTool + UI_EXECUTORS      ui-tools/registry.ts（参数第二道守卫）
 *  → ports.navigate                hooks/use-ui-tool-host.ts（组件里注入的真端口）
 *  → MemoryRouter 路由真变 + <UiActionBanner/> 真渲染
 * ```
 *
 * **为什么要端到端而不是各层单测**：2026-11-27 的 P0 就是「handler 返回的键名是
 * `ui_action`，而分发是写死的 `switch (event.type)`」——各层单测全绿，整条链路是死的
 * （模型照旧说「已帮你切过去」，页面一动不动，日志里一条错误都没有）。把 store /
 * streaming / handler / registry / 组件换成替身，等于把唯一会坏的那几处接缝换成自己的
 * 假设。所以这里只替换 `./api`，其余一律真货。
 *
 * 断言口径：只认律师能看见的东西——地址（`data-testid="loc"`，读真路由 location）、
 * 横幅文案、DOM 里的提示。运行记录只读 `uiToolRuns[callId]`（横幅与提示的输入就是它），
 * 不读 `seenCallIds` 这类执行期内部缓存。
 *
 * 失败/守护态（失败不淡出、未知动作、宿主未挂载、无 Router）在同目录
 * `ui-action.guard.dom.test.tsx`。
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { COPILOT_LAUNCH_EVENT } from './launch'
import { useCopilot } from './store'
import { UiActionBanner } from './components/UiActionBanner'
import { UiToolHost } from './components/UiToolHost'
import type { UiToolRun } from './state-types'
import type { AgentSession } from './types'

/**
 * 唯一的替身：HTTP 边界。**逐个列出导出**是硬要求——`vi.mock` 的工厂整体替换模块，
 * 少列一个符号，用到它的路径拿到的就是 `undefined`，报错却是 `x is not a function`。
 * 清单与 `api.ts`（含它 re-export 的 review/folders/memory/mention 四组）逐项对应。
 */
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

/** 后端某一轮的会话（`send` 无会话时先建一个，之后复用） */
const SESSION: AgentSession = {
  session_id: 's-1',
  title: '',
  status: 'active',
  llm_model: '',
  agent_kind: 'pi',
  created_at: '',
  updated_at: '',
}

/** 一次性吐完所有帧（不需要观察流当中的状态时用） */
function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

/** 可逐帧喂的响应：观察**流当中**的状态（同步消费完就什么都看不到了） */
function controlledStream() {
  const handles = { push: (_frame: string) => {}, close: () => {} }
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      handles.push = (frame: string) => controller.enqueue(encoder.encode(frame))
      handles.close = () => controller.close()
    },
  })
  return { resp: new Response(body, { status: 200 }), ...handles }
}

type Round = { stream: ReturnType<typeof controlledStream>; sending: Promise<void> }

const DONE_FRAME = 'data: {"type":"done","session_id":"s-1"}\n\n'

/** 一帧 `ui_action`（字段名照后端契约：`call_id` / `action` / `arguments`） */
function actionFrame(callId: string, action: string, args: Record<string, unknown>): string {
  return `data: ${JSON.stringify({ type: 'ui_action', call_id: callId, action, arguments: args, route: null })}\n\n`
}

/**
 * 地址探针：把真路由的 pathname+search 打到 DOM 上。
 *
 * `navigate` 被调用过 ≠ 地址变了（跳错 router、跳进通配重定向都会「调用成功」），
 * 所以断言一律读这里。`visitedKeys` 记每次提交过的 history key：「跳了几次」只有
 * 它能答（幂等用例要的正是这个）。
 */
const visitedKeys = new Set<string>()

function LocationProbe() {
  const { pathname, search, key } = useLocation()
  useEffect(() => {
    visitedKeys.add(key)
  }, [key])
  return <div data-testid="loc">{`${pathname}${search}`}</div>
}

function renderCopilot(options: { entries?: string[] } = {}) {
  const { entries = ['/'] } = options
  return render(
    <MemoryRouter initialEntries={entries}>
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
      {/* 生产里由 AppShell 的面板 / 助手页挂载：它才是 navigate 端口的注入点 */}
      <UiToolHost />
      <UiActionBanner />
    </MemoryRouter>,
  )
}

let roundCount = 0

/** 开一轮真对话的流（真 `send` 一路走到 `openMessageStream`） */
async function beginRound(text = '帮我把项目列表打开'): Promise<Round> {
  roundCount += 1
  const stream = controlledStream()
  vi.mocked(copilotApi.openMessageStream).mockResolvedValue(stream.resp)
  const sending = useCopilot.getState().send(text)
  await waitFor(() =>
    expect(vi.mocked(copilotApi.openMessageStream).mock.calls.length).toBeGreaterThanOrEqual(roundCount),
  )
  return { stream, sending }
}

/**
 * 喂若干帧并让处理器落完。
 *
 * 等的是一串**微任务**（不是时间：动作从受理到执行只有一个 await，几个微任务就收尾），
 * 所以这里数出来的节奏与机器快慢无关。
 */
async function feed(round: Round, ...frames: string[]) {
  await act(async () => {
    for (const frame of frames) round.stream.push(frame)
    for (let i = 0; i < 12; i += 1) await Promise.resolve()
  })
}

/** 收尾本轮（关流 + 等 send 结束）：不留悬挂的流到下一个用例 */
async function endRound(round: Round) {
  await act(async () => {
    round.stream.push(DONE_FRAME)
    round.stream.close()
  })
  await round.sending
}

/**
 * 在横幅给出「停下」的那一帧点它，返回此刻的横幅文案。
 *
 * 为什么不能「先 await 再点」：从受理到调用执行器之间只有一个 `await`，而三个执行器
 * 都是同步的，所以「AI 正在操作 + 停下」在 DOM 里只活一两个微任务——`await` 回来时
 * 横幅已经是「已完成」，按钮已经不在了。这不是取巧：点的仍然是横幅上的真按钮，
 * 只是把时机钉在运行态那一帧。
 */
async function clickStopWhileRunning(): Promise<string> {
  for (let i = 0; i < 24; i += 1) {
    await Promise.resolve()
    const banner = screen.queryByTestId('ui-action-banner')
    const stop = banner?.querySelector('button')
    if (banner && stop) {
      fireEvent.click(stop)
      return banner.textContent ?? ''
    }
  }
  throw new Error('横幅从未进入可打断的运行态（拿不到「停下」按钮）')
}

/**
 * 逐微任务记录横幅文案，直到本次发送结束。
 *
 * 用途同 `clickStopWhileRunning`：「运行态」短到 `await` 之后必然错过，而
 * 「动作期间律师看到了什么」是横幅存在的唯一理由，必须逐帧看。
 */
async function recordBanner(times = 40): Promise<string[]> {
  const seen: string[] = []
  for (let i = 0; i < times; i += 1) {
    await Promise.resolve()
    const banner = screen.queryByTestId('ui-action-banner')
    if (banner) seen.push(banner.textContent ?? '')
  }
  return seen
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
  visitedKeys.clear()
  roundCount = 0
  // jsdom 的地址栏不会跟着 MemoryRouter 走：每个用例从站内首页起步
  window.history.replaceState({}, '', '/')
  vi.mocked(copilotApi.createSession).mockResolvedValue(SESSION)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AI 操作页面：动作真的落到了律师眼前的页面上', () => {
  it('律师说「打开项目列表」→ 地址栏真的到 /projects（不是只调了 navigate）', async () => {
    renderCopilot()
    const round = await beginRound()

    await feed(round, actionFrame('nav-1', 'ui_navigate', { path: '/projects' }))

    expect(screen.getByTestId('loc').textContent).toBe('/projects')
    expect(runOf('nav-1')).toMatchObject({ name: 'ui_navigate', state: 'ok' })
    await endRound(round)
  })

  it('律师说「切到待处理」→ 材料预处理页停在 ?stage=todo', async () => {
    renderCopilot()
    const round = await beginRound('切到待处理')

    await feed(round, actionFrame('stage-1', 'ui_material_prep_set_stage', { stage: 'todo' }))

    expect(screen.getByTestId('loc').textContent).toBe('/material-prep?stage=todo')
    await endRound(round)
  })

  it('律师正开着某条消息（?message=abc）时切阶段 → 深链接没被抹掉', async () => {
    // 地址栏必须和路由是同一份地址：生产里 AppShell 是声明式 <BrowserRouter>，两者本来
    // 就一致；端口的 currentPath 读 window.location（见 hooks/use-ui-tool-host.ts），
    // jsdom 不会跟着 MemoryRouter 变，所以这里像真浏览器那样把地址摆到律师真实所在处。
    window.history.replaceState({}, '', '/material-prep?message=abc')
    renderCopilot({ entries: ['/material-prep?message=abc'] })
    const round = await beginRound('切成待处理')

    await feed(round, actionFrame('stage-2', 'ui_material_prep_set_stage', { stage: 'todo' }))

    // 切阶段只改 stage：?message= 是「打开某条消息」的直达能力，抹掉就等于把律师手上的
    // 那条消息弄丢了（use-desk-filters 的 setStage 同样是在现有参数上改）
    expect(screen.getByTestId('loc').textContent).toBe('/material-prep?message=abc&stage=todo')
    await endRound(round)
  })

  it('律师说「在张三这个案子里打开助手」→ 面板收到带案件上下文的打开指令', async () => {
    // 为什么监听 COPILOT_LAUNCH_EVENT，而不是 spy `../launch` 的 openCopilot：
    // 那个 window 事件才是 AppShell 真正消费的入口（chunk 未加载时还有
    // takePendingLaunchContext 兜底），把 launch 换成替身等于绕开被测接缝；
    // 而且本文件只允许替身 HTTP 边界。
    const launches: unknown[] = []
    const onLaunch = (event: Event) => launches.push((event as CustomEvent<unknown>).detail)
    window.addEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    renderCopilot()
    const round = await beginRound('在张三这个案子里打开助手')

    await feed(round, actionFrame('open-1', 'ui_copilot_open', { origin: 'case', refId: 812, title: '张三' }))

    window.removeEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    expect(launches).toEqual([{ origin: 'case', refId: 812, title: '张三' }])
    // 开面板不是导航：地址不该动
    expect(screen.getByTestId('loc').textContent).toBe('/')
    await endRound(round)
  })

  it('动作在飞时横幅说「正在操作」，落完转「已完成」，1.2 秒后淡出', async () => {
    vi.useFakeTimers()
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([actionFrame('banner-1', 'ui_navigate', { path: '/projects' }), DONE_FRAME]),
    )
    renderCopilot()

    let seen: string[] = []
    await act(async () => {
      const sending = useCopilot.getState().send('打开项目列表')
      seen = await recordBanner()
      await sending
    })

    // 运行态真的进过 DOM（不是「受理完就跳到终态」）
    expect(seen.some((text) => text.includes('AI 正在操作'))).toBe(true)
    expect(screen.getByTestId('ui-action-banner').textContent).toContain('AI 已完成')
    // 落完就不再给「停下」（动作已执行完，点了也没有可挡的东西）
    expect(screen.queryByRole('button', { name: '停下' })).toBeNull()

    // 落完立刻消失会让律师以为「什么都没发生」：先留住 1.2 秒
    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(screen.queryByTestId('ui-action-banner')).not.toBeNull()
    // 1.2 秒起淡出（opacity-0，仍在 DOM），1.5 秒后移出 DOM
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByTestId('ui-action-banner').className).toContain('opacity-0')
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByTestId('ui-action-banner')).toBeNull()
  })

  it('同一 call_id 被重投两次 → 页面只跳一次（模型重试不该让律师连跳两下）', async () => {
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        actionFrame('dup-1', 'ui_navigate', { path: '/projects' }),
        actionFrame('dup-1', 'ui_navigate', { path: '/projects' }),
        DONE_FRAME,
      ]),
    )
    renderCopilot()

    await act(async () => {
      await useCopilot.getState().send('打开项目列表')
    })

    expect(screen.getByTestId('loc').textContent).toBe('/projects')
    // 一次导航 = 一个新 history key：初始 '/' 一个 + 真正跳过去一个
    expect(visitedKeys.size).toBe(2)
  })

  it('律师点「停下」→ 同轮后续动作不再执行；下一轮重新开流后又能操作', async () => {
    renderCopilot()
    const first = await beginRound('打开项目列表')

    // 第一帧照常执行，并在横幅进入运行态的那一刻点「停下」
    let clicked = ''
    await act(async () => {
      first.stream.push(actionFrame('abort-1', 'ui_navigate', { path: '/projects' }))
      clicked = await clickStopWhileRunning()
    })
    expect(clicked).toContain('AI 正在操作')
    expect(useCopilot.getState().abortedAt).not.toBeNull()
    // 已发出的动作不追回：它在毫秒内就落完了（软打断只挡后续）
    expect(screen.getByTestId('loc').textContent).toBe('/projects')

    // 第二帧：律师已经点了停下 → 不执行，地址停在原处
    await feed(first, actionFrame('abort-2', 'ui_navigate', { path: '/settings' }))
    expect(screen.getByTestId('loc').textContent).toBe('/projects')
    expect(runOf('abort-2')).toMatchObject({ state: 'aborted', code: 'aborted' })
    await endRound(first)

    // 下一轮开流 = 上一轮的打断作废（不清就会「停下一次之后 AI 永远操作不了页面」）
    const second = await beginRound('再看看设置页')
    expect(useCopilot.getState().abortedAt).toBeNull()
    await feed(second, actionFrame('abort-3', 'ui_navigate', { path: '/settings' }))
    expect(screen.getByTestId('loc').textContent).toBe('/settings')
    await endRound(second)
  })

  it('模型编的危险地址（javascript: 与客户上传链接）都进不去，页面一动不动', async () => {
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        actionFrame('evil-1', 'ui_navigate', { path: 'javascript:alert(1)' }),
        // 链接即凭证：AI 把客户上传入口写进地址栏等于泄露它（见 ui-tools/routes.ts 三道排除）
        actionFrame('evil-2', 'ui_navigate', { path: '/u/abc' }),
        DONE_FRAME,
      ]),
    )
    renderCopilot()

    await act(async () => {
      await useCopilot.getState().send('跳过去')
    })

    expect(screen.getByTestId('loc').textContent).toBe('/')
    // 不在白名单里 = route_unreachable（安全拦截，不重试同参数），不是「参数类型错」
    expect(runOf('evil-1')).toMatchObject({ state: 'error', code: 'route_unreachable' })
    expect(runOf('evil-2')).toMatchObject({ state: 'error', code: 'route_unreachable' })
  })
})
