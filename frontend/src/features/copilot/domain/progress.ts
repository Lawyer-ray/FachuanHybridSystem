/**
 * 流式「还在干活」的观感口径：当前在调哪个工具、卡片该说哪句话。
 *
 * 纯函数，无 React。真实反馈：dsh / openai-agents 先调工具、工具调完才吐正文，
 * 网关 0.28s 就有 chunk，但界面在这段里什么都不显示——律师看到的是「另外两个
 * agent 2.4 秒就出字，这两个憋到 16 秒才一次性吐全文」。事件链路本来就通
 * （`tool_call` → 工具行），缺的是**把工具行放到正文区里、并说清正在干什么**。
 *
 * 这里只回答两个问题，渲染在 components/StreamActivity.tsx：
 * 1. {@link pendingToolCall}：这一栏此刻还在等哪个工具返回（→「正在查 XX…」）；
 * 2. {@link toolActionLabel}：这个工具名用中文怎么说（→「正在查客户信息…」）。
 */

import type { ChatMessage } from '../types'
import { shortToolName } from './reference'

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
  const pending = pendingToolCall(message.tools)
  if (pending) return `正在${toolActionLabel(pending.toolName)}…`
  if (message.tools && message.tools.length > 0) return '正在整理资料…'
  return null
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
