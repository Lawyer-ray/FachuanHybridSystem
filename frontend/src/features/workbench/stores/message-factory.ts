/** 工作台消息工厂函数 */

import type { WorkbenchMessage, StreamingMessage } from '../types'

/** 创建用户消息 */
export function createUserMessage(content: string): WorkbenchMessage {
  return {
    id: Date.now(),
    role: 'user',
    content,
    llm_model: '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: {},
    created_at: new Date().toISOString(),
  }
}

/** 从流式消息创建正式消息数组（包含工具调用消息和助手消息） */
export function finalizeStreamingMessages(streamingMessage: StreamingMessage | null): WorkbenchMessage[] {
  if (!streamingMessage) return []

  const messages: WorkbenchMessage[] = []

  // 工具调用消息
  for (const tc of streamingMessage.toolCalls) {
    messages.push({
      id: Date.now() + Math.random(),
      role: 'tool',
      content: `工具 ${tc.name}: ${tc.status === 'success' ? '成功' : tc.status === 'error' ? '失败' : '执行中'}`,
      llm_model: '',
      tool_call_id: tc.toolCallId,
      tool_name: tc.name,
      tool_input: tc.arguments,
      tool_output: tc.result ? { result: tc.result, success: tc.success } : {},
      metadata: { success: tc.success ?? (tc.status === 'success') },
      created_at: new Date().toISOString(),
    })
  }

  // 助手消息
  if (streamingMessage.content) {
    messages.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: streamingMessage.content,
      llm_model: streamingMessage.model || '',
      tool_call_id: '',
      tool_name: '',
      tool_input: {},
      tool_output: {},
      metadata: {},
      created_at: new Date().toISOString(),
    })
  }

  return messages
}

/** 创建中断消息 */
export function createAbortedMessage(content: string, model?: string): WorkbenchMessage {
  return {
    id: Date.now() + 1,
    role: 'assistant',
    content: content + '\n\n[已中断]',
    llm_model: model || '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: { aborted: true },
    created_at: new Date().toISOString(),
  }
}

/** 创建连接中断消息 */
export function createPartialMessage(content: string, model?: string): WorkbenchMessage {
  return {
    id: Date.now() + 1,
    role: 'assistant',
    content: content + '\n\n[连接中断，部分内容已保留]',
    llm_model: model || '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: { partial: true },
    created_at: new Date().toISOString(),
  }
}

/** 创建错误消息 */
export function createErrorMessage(error: string): WorkbenchMessage {
  return {
    id: Date.now() + 1,
    role: 'assistant',
    content: `请求失败: ${error}`,
    llm_model: '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: {},
    created_at: new Date().toISOString(),
  }
}

/** 创建批量分析消息 */
export function createBatchItemMessage(fileName: string, content: string, jobId: string): WorkbenchMessage {
  return {
    id: Date.now() + Math.random(),
    role: 'assistant',
    content: `### ${fileName}\n\n${content}`,
    llm_model: '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: { source: 'batch_item', job_id: jobId },
    created_at: new Date().toISOString(),
  }
}

/** 创建批量分析汇总消息 */
export function createBatchSummaryMessage(summary: string, jobId: string): WorkbenchMessage {
  return {
    id: Date.now() + 1,
    role: 'assistant',
    content: summary,
    llm_model: '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: { source: 'batch_analysis', job_id: jobId },
    created_at: new Date().toISOString(),
  }
}
