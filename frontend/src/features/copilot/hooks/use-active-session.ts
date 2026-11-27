/**
 * 当前会话的装配与派生信息：抽屉面板（CopilotPanel）与独立页（AssistantPage）共用。
 *
 * 为什么抽出来：AI 助手有两个宿主——壳层里的抽屉，和 /assistant 的全宽页面。两者
 * 共用同一个 store，**挂载期的装配只能有一份**：恢复上次会话、拉后端清单、消费
 * 业务页的启动上下文（案件/合同页的「AI 助手」按钮）、拉待审列表、按业务范围拉
 * 会话列表取标题/模型/后端能力、流结束失效列表缓存、后台任务跑完重拉转录。
 * 页面若照抄一遍，加一条装配（比如新的清单接口）就得改两处，漏掉的那处表现为
 * 「同一个会话在两个宿主里表现不一样」。
 *
 * 这里只放与布局无关的部分：面板宽度、会话栏开关、并排模式仍归各宿主自己。
 */

import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { COPILOT_LAUNCH_EVENT, takePendingLaunchContext, type CopilotLaunchContext } from '../launch'
import { SESSIONS_QUERY_PREFIX, sessionsQueryOptions } from '../session-queries'
import { useCopilot } from '../store'
import { resolveCapabilities } from '../store/backends'

/** 宿主头部要显示的派生信息（全部来自会话列表缓存 / 后端清单） */
export interface ActiveSessionInfo {
  /** 当前会话标题；空串 = 列表还没回来，宿主自行回落默认标题 */
  currentTitle: string
  /** 最近一轮实际使用的模型（空串不显示标签） */
  currentModel: string
  /** 当前会话的后端 kind；null = 还没有会话（后端可自由选） */
  currentAgentKind: string | null
  /** 当前会话（或将要新建的会话）所用后端的能力声明 */
  currentCapabilities: Record<string, boolean>
}

export function useActiveSession(): ActiveSessionInfo {
  const sessionId = useCopilot((s) => s.sessionId)
  const streaming = useCopilot((s) => s.streaming)
  const context = useCopilot((s) => s.context)
  const switchSession = useCopilot((s) => s.switchSession)
  const enterContext = useCopilot((s) => s.enterContext)
  const loadPendingApprovals = useCopilot((s) => s.loadPendingApprovals)
  const loadPendingQuestions = useCopilot((s) => s.loadPendingQuestions)
  const refreshHistory = useCopilot((s) => s.refreshHistory)
  const loadBackends = useCopilot((s) => s.loadBackends)
  const backends = useCopilot((s) => s.backends)
  const selectedAgentKind = useCopilot((s) => s.selectedAgentKind)
  const hydrateAnswerModels = useCopilot((s) => s.hydrateAnswerModels)
  const seedAnswerModel = useCopilot((s) => s.seedAnswerModel)
  const queryClient = useQueryClient()

  // 恢复上次会话的历史（StrictMode 双挂载幂等：同 id 重拉无害）
  useEffect(() => {
    void switchSession(sessionId)
    // 只在**挂载时**取一次 sessionId：它是「上次打开的是哪个会话」的快照，之后
    // 跟着 sessionId 变化重跑就是每切一次会话再多拉一次历史（切换本身已经拉过）。
    // switchSession 是 zustand 稳定引用，不进 deps 不会取到旧闭包。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 可选 agent 后端清单：切换器的数据源。拉取失败静默（切换器退化为纯展示，
  // 发消息仍走后端默认 pi），所以不阻塞宿主打开。
  useEffect(() => {
    void loadBackends()
  }, [loadBackends])

  // 业务页打开入口（案件/合同页的「AI 助手」按钮）：
  // ①面板尚未挂载时 chunk 加载完从这里取走 pending；②已打开时监听后续事件切上下文
  useEffect(() => {
    const pending = takePendingLaunchContext()
    if (pending) void enterContext(pending)
    const onLaunch = (e: Event) => {
      const detail = (e as CustomEvent<CopilotLaunchContext | null>).detail
      if (detail) void enterContext(detail)
    }
    window.addEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    return () => window.removeEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    // 事件订阅只能挂一次：重复执行会二次 consume pending 启动上下文（第二个宿主
    // 拿到一个已经被取走的 context，表现为「点了 AI 助手但没进案件」）。
    // enterContext 是 zustand 稳定引用，不随渲染变。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 离线审批入口：宿主打开、每轮流结束、切会话后拉一次待审列表。
  // 后台任务挂起的高危工具调用由此浮出水面，而不是默默超时。
  useEffect(() => {
    if (!streaming) void loadPendingApprovals()
  }, [streaming, sessionId, loadPendingApprovals])

  // 待答提问同口径补拉：模型反问时若页面关着（后台任务/换设备），事件早已错过，
  // 但问题仍在服务端待答——不补拉的话模型只能按假设继续，律师事后无从得知
  useEffect(() => {
    if (!streaming) void loadPendingQuestions()
  }, [streaming, sessionId, loadPendingQuestions])

  // 会话列表按业务范围取：context（案件/合同页打开）时只列该范围的会话；
  // scopeKey 进 queryKey 保证两套列表缓存互不串
  const scopeKey = context ? `${context.origin}:${context.refId}` : 'all'
  const scope = context ? { origin: context.origin, refId: context.refId } : undefined
  const sessionsQuery = useQuery({
    // key / 页大小 / 取数统一在 session-queries（与 SessionSidebar、路由判据同一份）
    ...sessionsQueryOptions(scopeKey, scope),
    enabled: Boolean(sessionId) || Boolean(context),
  })
  const currentSession = sessionId ? sessionsQuery.data?.find((s) => s.session_id === sessionId) : undefined
  // 会话的后端只能从列表缓存读：store 不存它（新会话的归属由本轮勾选推导，见
  // store/turn.ts）。缓存未到 / 新对话时为 null，header 因此不画后端后缀——新对话
  // 本来就没有已定的后端，选谁在输入区的 AnswerAgentMenu。
  const currentAgentKind = currentSession?.agent_kind ?? null

  // 切会话 / 首次打开：先把**这个会话上次选的模型**装回来（localStorage）。
  // 不做这一步，刷新一次模型就回到默认——律师的期待是「这个会话继续用它」。
  useEffect(() => {
    hydrateAnswerModels(sessionId)
  }, [sessionId, hydrateAnswerModels])

  // 本地没选过时，用服务端记录的「上一轮实际用的模型」兜底（`AgentSession.llm_model`
  // 由 stream 层回写）。这条让**换浏览器/换设备**也能续上，而 localStorage 只管
  // 「刚选还没跑」的那一小段。
  useEffect(() => {
    const kind = currentSession?.agent_kind
    const model = currentSession?.llm_model
    if (kind && model) seedAnswerModel(kind, model)
  }, [currentSession?.agent_kind, currentSession?.llm_model, seedAnswerModel])

  // 每轮流结束后刷新会话列表：首条消息会自动生成标题，标题要能浮上来
  useEffect(() => {
    if (!streaming && (sessionId || context)) {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_PREFIX })
    }
  }, [streaming, sessionId, context, queryClient])

  // 后台任务跑完（updated_at 变化）自动重拉转录：任务的通知消息/产出
  // 不在宿主的流式路径里，只能靠轮询发现的 updated_at 变化来刷新。
  // 对话式会话不走这里（store 已实时追加，重拉只会浪费一次请求）。
  const prevTaskUpdatedRef = useRef('')
  useEffect(() => {
    if (currentSession?.origin !== 'task') return
    const updatedAt = currentSession.updated_at
    if (!updatedAt || updatedAt === prevTaskUpdatedRef.current) return
    const isFirst = prevTaskUpdatedRef.current === ''
    prevTaskUpdatedRef.current = updatedAt
    if (!isFirst && !streaming) void refreshHistory()
  }, [currentSession, streaming, refreshHistory])

  return {
    currentTitle: currentSession?.title ?? '',
    currentModel: currentSession?.llm_model ?? '',
    currentAgentKind,
    // 当前会话所用后端的能力声明：输入区据此隐藏插话入口（`steer=false` 的后端
    // 会把用户敲进去的话丢掉而不报错，比直接禁用糟糕得多）。新对话时按「将要
    // 新建的会话」算，避免建会话前的界面上已经少了一块。
    currentCapabilities: resolveCapabilities(backends, currentAgentKind ?? selectedAgentKind),
  }
}
