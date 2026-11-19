/**
 * SSE 流事件类型（自动生成——python -m apps.agent.sse_types --ts）
 * 后端单一来源：apps/agent/sse_types.py；修改须同步重新生成。
 *
 * 生成器是**反射**而不是手写模板：字段名与可选性只有 pydantic 一个来源。
 * 改契约请改 pydantic 模型再重跑上面那条命令，不要手改本文件
 * （CI 的 test_sse_contract_same_source.py 会逐字节比对）。
 */

export type AgentStreamEvent =
  | {
    type: 'meta'
    run_id?: string
    agent?: string
    session_id: string
    agents?: string[]
  }
  | {
    type: 'activity'
    run_id?: string
    agent?: string
    status: string
    agents?: string[]
    position?: number
    reason?: string
  }
  | {
    type: 'delta'
    run_id?: string
    agent?: string
    content: string
  }
  | {
    type: 'thinking'
    run_id?: string
    agent?: string
    content: string
  }
  | {
    type: 'tool_call'
    run_id?: string
    agent?: string
    tool_call_id: string
    name: string
    arguments?: unknown
  }
  | {
    type: 'tool_result'
    run_id?: string
    agent?: string
    tool_call_id: string
    name: string
    result?: string
    is_error?: boolean
  }
  | {
    type: 'approval_request'
    run_id?: string
    agent?: string
    approval_id: string
    tool_name: string
    tool_args?: Record<string, unknown>
    message?: string
    risk_level?: string
    needs_second_confirmation?: boolean
  }
  | {
    type: 'usage'
    run_id?: string
    agent?: string
    output_tokens: number
    input_tokens?: number
    cache_read_tokens?: number
    cache_write_tokens?: number
  }
  | {
    type: 'question_request'
    run_id?: string
    agent?: string
    question_id: string
    questions?: Record<string, unknown>[]
    timeout_seconds?: number
  }
  | {
    type: 'compaction'
    run_id?: string
    agent?: string
    phase: 'start' | 'end'
  }
  | {
    type: 'error'
    run_id?: string
    agent?: string
    message: string
  }
  | {
    type: 'unknown'
    run_id?: string
    agent?: string
    raw?: Record<string, unknown>
  }
  | {
    type: 'done'
    run_id?: string
    agent?: string
    session_id: string
    agents?: string[]
    message_id?: number
    finish_reason?: 'ok' | 'degraded' | 'error' | 'cancelled'
    context_used_tokens?: number
    context_total_tokens?: number
  }
