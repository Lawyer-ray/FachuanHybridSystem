/**
 * SSE 流事件类型（自动生成——python -m apps.agent.sse_types --ts）
 * 后端单一来源：apps/agent/sse_types.py；修改须同步重新生成。
 */

export type AgentStreamEvent =
  | { type: 'meta'; session_id: string; agent?: string }
  | { type: 'activity'; status: string; agent?: string; position?: number }
  | { type: 'delta'; content: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool_call_id: string; name: string; arguments?: unknown }
  | { type: 'tool_result'; tool_call_id: string; name: string; result?: string; is_error?: boolean }
  | {
      type: 'approval_request'
      approval_id: string
      tool_name: string
      tool_args?: Record<string, unknown>
      message: string
      risk_level?: string
      needs_second_confirmation?: boolean
    }
  | {
      type: 'usage'
      output_tokens: number
      input_tokens: number
      cache_read_tokens: number
      cache_write_tokens: number
    }
  | {
      type: 'question_request'
      question_id: string
      questions: Array<Record<string, unknown>>
      timeout_seconds: number
    }
  | { type: 'error'; message: string }
  | { type: 'compaction'; phase: 'start' | 'end' }
  | { type: 'done'; session_id: string; context_used_tokens?: number; context_total_tokens?: number }
