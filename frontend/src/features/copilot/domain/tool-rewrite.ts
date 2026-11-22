/**
 * `rewrite_folder_file` 的识别与信号收窄（纯函数）。
 *
 * 原文/改写全文**只在 tool_call 的参数里完整到达**：tool_result 的 `result` 被 SSE
 * 截到 2000 字，靠它读不回正文。落盘成功时把这对字段带进 file-rewritten 事件，
 * 打开中的画布就能就地落修订（免整页重载）。
 *
 * 缓存本身（按 tool_call_id 存一对参数）留在 `handlers/tool-handlers.ts` 的闭包里：
 * 那是本轮的临时状态，轮结束即回收；本文件只做「认不认得这个工具」的判定。
 */

import { extractRewriteArgs, parseFileRewrite, type FileRewriteSignal } from './reference'

/** 一次改写调用的原文与改写全文 */
export interface RewriteArgs {
  original: string
  replacement: string
}

/**
 * 这次工具调用是不是 `rewrite_folder_file`；是则解析出参数。
 *
 * 参数是**渐进到达**的（同一次调用可能分几帧补齐），调用方按 tool_call_id 覆盖写入
 * 即可，以完整到达的那条为准。
 */
export function rewriteCallOf(event: {
  name?: string
  tool_call_id?: string
  arguments: unknown
}): { toolCallId: string; args: RewriteArgs } | null {
  // 后端工具名可能带命名空间前缀（`mcp__fachuan__rewrite_folder_file`），按后缀认
  if (!event.name?.endsWith('rewrite_folder_file') || !event.tool_call_id) return null
  const args = extractRewriteArgs(event.arguments)
  return args ? { toolCallId: event.tool_call_id, args } : null
}

/**
 * tool_result + 同次调用的参数 → 要广播给画布的改写信号。
 *
 * 失败、非改写工具、结果里没有可定位的归属时返回 null（调用方据此不发事件）。
 */
export function fileRewriteSignalOf(
  event: { name?: string; result?: unknown; is_error?: boolean },
  args?: RewriteArgs,
): FileRewriteSignal | null {
  // result 在事件类型里是 unknown：非字符串（对象/数组）不可能带出归属信息，直接按空串处理，
  // 避免 String({}) 变成 '[object Object]' 这种无意义输入
  const raw = typeof event.result === 'string' ? event.result : ''
  return parseFileRewrite(event.name, raw, event.is_error === true, args)
}
