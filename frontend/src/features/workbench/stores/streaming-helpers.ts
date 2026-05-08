/** 工作台流式发送辅助函数 */

import type { SSEEvent, StreamingMessage, ToolCallState } from '../types'

/**
 * 连接 SSE 流并读取事件
 * 返回一个 Promise，在流结束或出错时 resolve
 */
export async function connectAndReadStream(
  url: string,
  headers: Record<string, string>,
  body: object | undefined,
  abortSignal: AbortSignal | undefined,
  onEvent: (event: SSEEvent) => void,
  onLastEventId: (id: string) => void,
): Promise<void> {
  const response = await fetch(url, {
    method: 'POST',
    signal: abortSignal,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No reader')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') continue

      try {
        const event = JSON.parse(data) as SSEEvent
        if (event.type === 'meta' && event.session_id) {
          onLastEventId(event.session_id)
        }
        onEvent(event)
      } catch { /* skip malformed */ }
    }
  }
}

/**
 * 处理 SSE 事件，更新 StreamingMessage
 */
export function reduceStreamingMessage(sm: StreamingMessage, event: SSEEvent): StreamingMessage {
  switch (event.type) {
    case 'meta':
      return {
        ...sm,
        model: event.model,
        activeAgent: event.agent || sm.activeAgent,
        currentActivity: event.agent ? `${event.agent} 正在思考...` : sm.currentActivity,
      }

    case 'activity':
      return {
        ...sm,
        activeAgent: event.agent || sm.activeAgent,
        currentActivity: event.status === 'thinking'
          ? `${event.agent || sm.activeAgent || '助手'} 正在思考...`
          : sm.currentActivity,
      }

    case 'delta':
      return {
        ...sm,
        content: sm.content + (event.content || ''),
        currentActivity: undefined,
      }

    case 'tool_call': {
      const tc: ToolCallState = {
        toolCallId: event.tool_call_id || '',
        name: event.name || event.tool_name || '',
        arguments: event.arguments || event.tool_input || {},
        status: 'running',
      }
      const toolName = event.name || event.tool_name || '工具'
      return {
        ...sm,
        toolCalls: [...sm.toolCalls, tc],
        currentActivity: `正在执行 ${toolName}...`,
      }
    }

    case 'tool_result': {
      const toolCallId = event.tool_call_id || ''
      return {
        ...sm,
        toolCalls: sm.toolCalls.map((tc) =>
          tc.toolCallId === toolCallId
            ? {
                ...tc,
                result: event.result ?? event.tool_output,
                success: event.success,
                status: event.success === false ? 'error' as const : 'success' as const,
              }
            : tc,
        ),
        currentActivity: undefined,
      }
    }

    case 'handoff':
      return {
        ...sm,
        handoffs: [
          ...sm.handoffs,
          { from: event.from_agent || '', to: event.to_agent || '' },
        ],
        currentActivity: `切换到 ${event.to_agent || '助手'}...`,
      }

    case 'error':
      return {
        ...sm,
        error: event.message || '未知错误',
      }

    default:
      return sm
  }
}

/**
 * 匹配【案例元数据汇总】块（兼容有无代码块包裹），用于前端展示时去除
 */
const METADATA_BLOCK_RE = /```[^\n]*\n\s*【案例元数据汇总】\s*\n[\s\S]*?\n\s*```\s*$|【案例元数据汇总】\s*\n[\s\S]*$/g

/** 去除分析结果中的元数据汇总块，只保留分析正文 */
export function stripMetadataBlock(text: string): string {
  return text.replace(METADATA_BLOCK_RE, '').trim()
}
