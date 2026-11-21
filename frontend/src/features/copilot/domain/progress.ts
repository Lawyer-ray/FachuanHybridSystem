/**
 * 流式「还在干活」的观感口径：当前在调哪个工具、卡片该说哪句话。
 *
 * 纯函数，无 React。真实反馈：dsh / openai-agents 先调工具、工具调完才吐正文，
 * 网关 0.28s 就有 chunk，但界面在这段里什么都不显示——律师看到的是「另外两个
 * agent 2.4 秒就出字，这两个憋到 16 秒才一次性吐全文」。事件链路本来就通
 * （`tool_call` → 工具行），缺的是**把工具行放到正文区里、并说清正在干什么**。
 *
 * 这里只回答三个问题：
 * 1. {@link applyToolCall} / {@link applyToolResult}：一次工具调用落到**两个位置**
 *    ——转录里的工具行、气泡上的活动行（纯变换，turn-handlers 只负责写 store）；
 * 2. {@link currentTool} / {@link pendingToolCall}：这一栏此刻还在等哪个工具返回
 *    （→「正在查 XX…」）；
 * 3. {@link toolActionLabel}：这个工具名用中文怎么说（→「正在查客户信息…」）。
 *
 * ## 工具的两个来源（踩过的坑）
 *
 * 多栏时工具挂在 `message.tools`（`mergeAgentAnswers` 填的**渲染槽**，栏头下那串
 * chip）；单栏时 `tools` 永远是 undefined——于是本模块早先直接返回 null，界面上
 * 什么都不显示。而那正是事故现场：dsh / openai-agents 先调工具、调完才吐正文，
 * 中间十几次读秒一片空白（律师以为是卡死）。所以单栏改用 `message.pendingTool`
 * （见 turn-handlers 的 onToolCall / onToolResult），本模块对两者一视同仁。
 */

import type { ChatMessage } from '../types'
import { shortToolName } from './reference'
import { nextLocalId } from './sse'

/**
 * 结果为空时给 `pendingTool.content` 的哨兵。
 *
 * `content` 是必填 string，空串与「还在等」在 ChatMessage 上不可区分，于是空结果的
 * 工具会让界面永远停在「正在查 XX…」。这个字段从不渲染（见 {@link activityText}），
 * 所以哨兵不会漏到屏幕上。
 */
export const EMPTY_TOOL_RESULT = '（无返回内容）'

/** 一次 `tool_call` 事件里与本模块有关的部分（事件对象里其余字段是给别处用的） */
export interface ToolCallInput {
  toolCallId?: string
  toolName?: string
  /** 多答时哪个 agent 调的（工具行要带来源，否则回放时分不出证据归谁） */
  agentKind?: string
  /** `rewrite_folder_file` 的参数解析结果；其他工具为 undefined */
  rewrite?: ChatMessage['rewrite']
  /** 执行态（缺省 `running`：`tool_call` 到达即视为开始） */
  toolState?: ChatMessage['toolState']
  /** 开始时刻（ms）。由调用方取 `Date.now()`——本模块是纯函数，不读时钟。 */
  startedAt?: number
  /** 工具入参（只用于生成「读取 X」这类短标题） */
  toolArgs?: unknown
}

/** 一次 `tool_result` 事件里与本模块有关的部分 */
export interface ToolResultInput {
  toolCallId?: string
  result: string
  /**
   * 结算态：成功 / 失败 / 被中止。
   *
   * **必须由事件给**（`tool_result.is_error` / 停止信号），不能由 `result` 是否为空
   * 推断：删除类工具的合法结果就是空串，按空字符串判失败会把「成功」显示成「失败」。
   */
  toolState?: Extract<ChatMessage['toolState'], 'ok' | 'error' | 'stopped'>
  /** 结束时刻（ms）；缺省表示时刻未知（历史数据 / 注入实现） */
  endedAt?: number
}

/**
 * `tool_call` → 新的 messages：新增/更新**转录工具行**，并在所属气泡上挂
 * {@link ChatMessage.pendingTool}。
 *
 * 一次调用为什么落到两个位置：
 * - 工具行（`role:'tool'`）是回放与核对的依据（改名/结果/修订块都在那），
 *   单栏按时间平铺、多栏归到各栏 chip；
 * - `pendingTool` 只喂活动行（「正在查 XX…」）。**不能**把单栏的工具也写进
 *   `tools`：那是多栏的渲染槽，写了工具行会渲染两份。
 *
 * 返回**原数组引用** = 什么都没变（pi 对同一次调用会重复发 `message_end`，
 * 每次都写状态会让整段转录白白重渲染）。
 */
export function applyToolCall(
  messages: ChatMessage[],
  ownerId: string,
  call: ToolCallInput,
): ChatMessage[] {
  const callId = call.toolCallId ?? ''
  const existing = callId
    ? messages.find((m) => m.role === 'tool' && m.toolCallId === callId)
    : undefined
  let next = messages
  if (existing) {
    // 参数渐进完整：后到的解析结果覆盖前一条，不新增行
    if (call.rewrite || call.toolArgs !== undefined) {
      next = messages.map((m) =>
        m === existing
          ? { ...m, ...(call.rewrite ? { rewrite: call.rewrite } : {}), ...(call.toolArgs !== undefined ? { toolArgs: call.toolArgs } : {}) }
          : m,
      )
    }
  } else {
    next = [
      ...messages,
      {
        id: nextLocalId(),
        role: 'tool',
        content: '',
        toolName: call.toolName,
        ...(callId ? { toolCallId: callId } : {}),
        ...(call.rewrite ? { rewrite: call.rewrite } : {}),
        ...(call.agentKind ? { agentKind: call.agentKind } : {}),
        // 五态与耗时的起点：律师要回答「这个工具跑了多久」，必须从声明那刻记
        toolState: call.toolState ?? 'running',
        ...(call.startedAt !== undefined ? { toolStartedAt: call.startedAt } : {}),
        ...(call.toolArgs !== undefined ? { toolArgs: call.toolArgs } : {}),
      },
    ]
  }
  return withPendingTool(next, ownerId, call)
}

/**
 * 在**指定气泡**上挂「此刻在等哪个工具」。
 *
 * 只改 `ownerId` 这一条：多答时两栏的工具交错到达，写错一栏就会让 pi 那边显示
 * 「正在查案件列表…」（dsh 的工具）——看起来正常，实际全是别人的活。
 */
function withPendingTool(messages: ChatMessage[], ownerId: string, call: ToolCallInput): ChatMessage[] {
  const callId = call.toolCallId ?? ''
  const marked = (m: ChatMessage) =>
    callId ? m.pendingTool?.toolCallId === callId : m.pendingTool !== undefined
  let changed = false
  const next = messages.map((m) => {
    if (m.id !== ownerId || marked(m)) return m
    changed = true
    return {
      ...m,
      pendingTool: {
        // id 用 tool_call_id：天然唯一，回调时一眼能对上是哪次调用
        id: callId || nextLocalId(),
        role: 'tool' as const,
        content: '',
        toolName: call.toolName,
        ...(callId ? { toolCallId: callId } : {}),
      },
    }
  })
  return changed ? next : messages
}

/**
 * `tool_result` → 新的 messages：工具行填结果，气泡上的 `pendingTool` 置**已完成**。
 *
 * 为什么置「已完成」而不是清空：清空后「工具都回来了、正文还没来」与「一次都没
 * 调过」不可区分，界面会在律师最需要一句交代的时候突然白回去（正文往往还要等
 * 好几秒）。已完成与待返回靠 `content` 是否为空区分（见 {@link currentTool}）。
 */
export function applyToolResult(
  messages: ChatMessage[],
  ownerId: string,
  res: ToolResultInput,
): ChatMessage[] {
  const matchId = res.toolCallId ?? ''
  const settled = res.result || EMPTY_TOOL_RESULT
  return messages.map((m, i) => {
    // tool_call 与 tool_result 以 tool_call_id 归并；缺 id 时落最近一个空 tool 行
    const byId = Boolean(matchId) && m.role === 'tool' && m.toolCallId === matchId
    const lastEmpty =
      !matchId && m.role === 'tool' && !m.content && messages.slice(i + 1).every((x) => x.role !== 'tool')
    if (byId || lastEmpty) {
      return {
        ...m,
        content: res.result,
        ...(res.toolState ? { toolState: res.toolState } : {}),
        ...(res.endedAt !== undefined ? { toolEndedAt: res.endedAt } : {}),
      }
    }
    if (m.id !== ownerId || !m.pendingTool) return m
    // 不是这次调用的结果：别人的工具不影响本栏的「正在查」
    if (matchId && m.pendingTool.toolCallId !== matchId) return m
    if (!matchId && m.pendingTool.content) return m
    return { ...m, pendingTool: { ...m.pendingTool, content: settled } }
  })
}

/**
 * 这一栏现在的活动说明；`null` = 不该显示活动行。
 *
 * 三档按「这段时间里到底在发生什么」分，不按事件类型分——律师关心的是
 * 「它在查东西 / 它在写」，而不是 SSE 的类型名：
 * - 有工具未返回 → 正在查 XX…（最具体的一档，工具名翻成中文动作）
 * - 工具全回来了、正文还没来 → 正在整理资料…（模型在消化工具结果）
 * - 思考中 / 已失败 / 正在出正文 → `null`（各有自己的显示：思考块、`本轮未做`、
 *   正文与光标）
 *
 * 「没有任何工具、也没有思考、纯空白」这一档在流式开头只有几百毫秒，刻意留空：
 * 凭空说一句「正在思考…」在思考模式关闭时是不成立的叙述，模型此时可能正在
 * 决定要不要调工具。
 */
export function activityText(message: ChatMessage): string | null {
  if (message.streaming !== true || message.failed) return null
  // 正文或思考一出现，各自的块就接管了「还活着」的叙事
  if (message.content || message.thinking) return null
  const tool = currentTool(message)
  // 还没回来（content 空）→ 说清在查什么；已回来（content 非空，见
  // turn-handlers 的 onToolResult）→ 落到下一档「整理资料」
  if (tool && !tool.content) return `正在${toolActionLabel(tool.toolName)}…`
  if (tool) return '正在整理资料…'
  if (message.tools && message.tools.length > 0) return '正在整理资料…'
  return null
}

/**
 * 这条气泡此刻的焦点工具：多栏看 `tools`，单栏看 `pendingTool`。
 *
 * 顺序不能反：多栏的 `tools` 是本轮**全部**工具的历史，`pendingTool` 只是最后一枚；
 * 先问 `tools` 才能保证「并行调了三个、还差最早那个没回来」时显示的是它。
 * 两边都空 = 这一轮还没调过工具，调用方不要编造一个焦点。
 */
export function currentTool(message: ChatMessage): ChatMessage | null {
  return pendingToolCall(message.tools) ?? message.pendingTool ?? null
}

/**
 * 这一栏此刻正在等返回的工具调用（按到达顺序取**最后一条未完成**的）。
 *
 * 为什么取最后一条而不是第一条：模型偶尔并行调多个工具，界面只需要一个焦点
 * （最近发起的那个就是当前动作）；把「还有 3 个没回来」也画出来会变成一堵墙。
 *
 * 已完成的工具（`content` 非空）不算：它的结果已经回来了，此刻卡住的是下一个。
 * 没有任何未完成工具时返回 `null`——包括「工具全回来了、正文还没开始」这个
 * 空档，那时由 {@link hasToolActivity} 的调用方显示「整理资料」而不是留白。
 */
export function pendingToolCall(tools: readonly ChatMessage[] | undefined): ChatMessage | null {
  if (!tools || tools.length === 0) return null
  for (let i = tools.length - 1; i >= 0; i -= 1) {
    const tool = tools[i]!
    if (!tool.content) return tool
  }
  return null
}

/**
 * 工具名 → 律师看得懂的动作词（「正在查客户信息…」的中间那截）。
 *
 * 为什么要有这层映射而不是直接显示工具名：`get_current_user` / `list_lawyers`
 * 是给机器看的，律师读到只会觉得「这是程序内部的东西」。查表覆盖的是 API 目录里
 * **高频且语义明确**的那批工具；没收录的回落为工具短名（`shortToolName`），
 * 它至少比什么都不显示更接近「在干什么」，也不会因为工具改名而显示错话。
 *
 * 命名按「动作 + 对象」：查客户信息 / 查案件 / 读文件 / 检索法条…，与
 * {@link toolActionLabel} 的句式「正在{动作}…」拼起来是通顺的中文。
 */
const TOOL_ACTIONS: Record<string, string> = {
  get_current_user: '确认身份',
  list_lawyers: '查律师名单',
  get_lawyer: '查律师信息',
  list_clients: '查客户名单',
  get_client: '查客户信息',
  list_cases: '查案件列表',
  get_case: '查案件信息',
  search_cases: '检索案件',
  list_contracts: '查合同列表',
  get_contract: '查合同信息',
  search_contracts: '检索合同',
  list_folder: '浏览文件夹',
  list_folder_files: '浏览材料目录',
  find_folder_file: '定位材料文件',
  read_folder_file: '读材料文件',
  read_agent_attachment: '读附件',
  rewrite_folder_file: '改写文件',
  apply_revision: '落修订',
  tool_search: '检索可用工具',
  web_search: '检索网络资料',
  search_law: '检索法条',
  search_judgments: '检索裁判文书',
  query_memory: '查记忆库',
  save_memory: '记入记忆',
}

/**
 * 工具名 → 「在干什么」的完整动作词。
 *
 * 入参应当已经过 `shortToolName` 归一（去掉 `mcp__fachuan__` 前缀）——两张表
 * 都用归一后的名字做键，且 `tool_call` 事件与工具行的 `toolName` 已经存的就是
 * 归一前的原名，所以这里自己再归一一次，调用方不必操心。
 */
export function toolActionLabel(name: string | undefined): string {
  const short = shortToolName(name)
  return TOOL_ACTIONS[short] ?? short
}
