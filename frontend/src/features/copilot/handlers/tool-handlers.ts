/**
 * 工具事件处理器：工具行走状态机（domain/progress）+ `rewrite_folder_file` 的
 * 参数缓存与跨 feature 广播。
 *
 * 参数缓存（按 tool_call_id）只活在**本轮**闭包里：轮结束随闭包回收，无跨轮泄漏。
 * 判定与收窄是纯函数，见 `domain/tool-rewrite.ts`。
 */

import { applyToolCall, applyToolResult } from '../domain'
import { fileRewriteSignalOf, rewriteCallOf, type RewriteArgs } from '../domain/tool-rewrite'
import { FILE_REWRITTEN_EVENT } from '../launch'
import type { StreamHandlers } from '../streaming'
import type { TurnHandlerContext } from './context'

export function createToolHandlers(
  ctx: TurnHandlerContext,
): Pick<StreamHandlers, 'onToolCall' | 'onToolResult'> {
  const { set, targetOf } = ctx

  /** rewrite_folder_file 各调用的参数（key = tool_call_id，见 domain/tool-rewrite） */
  const rewriteArgsById = new Map<string, RewriteArgs>()

  const onToolCall: StreamHandlers['onToolCall'] = (event, origin) => {
    // rewrite_folder_file：参数渐进完整时后一条覆盖前一条（以完整到达为准）
    // arguments 在事件类型里是可选的；显式补成必填字段再传，语义不变（缺省即 undefined）
    const call = rewriteCallOf({
      name: event.name,
      tool_call_id: event.tool_call_id,
      arguments: event.arguments,
    })
    if (call) rewriteArgsById.set(call.toolCallId, call.args)
    set((s) => {
      // 工具调用的两层落点（转录工具行 + 气泡上的活动行）都在 domain/progress：
      // 这里只管本轮修订参数缓存与写状态。返回原引用 = 什么都没变（不写状态）。
      const messages = applyToolCall(s.messages, targetOf(origin.kind), {
        ...(event.tool_call_id ? { toolCallId: event.tool_call_id } : {}),
        toolName: event.name,
        ...(origin.kind ? { agentKind: origin.kind } : {}),
        ...(call ? { rewrite: call.args } : {}),
        // 五态与耗时的起点：从「声明了这次调用」那一刻开始算，而不是结果回来才记
        toolState: 'running',
        startedAt: Date.now(),
        toolArgs: event.arguments,
      })
      return messages === s.messages ? s : { messages }
    })
  }

  const onToolResult: StreamHandlers['onToolResult'] = (event, origin) => {
    // 成功/失败由事件说了算（`is_error`），不由结果文本是否为空推断
    set((s) => ({
      messages: applyToolResult(s.messages, targetOf(origin.kind), {
        ...(event.tool_call_id ? { toolCallId: event.tool_call_id } : {}),
        result: String(event.result ?? ''),
        toolState: event.is_error === true ? 'error' : 'ok',
        endedAt: Date.now(),
      }),
    }))
    // AI 把修订写回文件夹文件（rewrite_folder_file 落盘成功）：广播给正打开该文件的
    // 编辑器画布。带 original/replacement（来自同次调用的参数）时画布优先**就地落
    // 修订**（插件桥），失败或缺参才换 key 重载
    const args = event.tool_call_id ? rewriteArgsById.get(event.tool_call_id) : undefined
    if (event.tool_call_id) rewriteArgsById.delete(event.tool_call_id)
    const rewrite = fileRewriteSignalOf(event, args)
    if (rewrite) {
      window.dispatchEvent(new CustomEvent(FILE_REWRITTEN_EVENT, { detail: rewrite }))
    }
  }

  return { onToolCall, onToolResult }
}
