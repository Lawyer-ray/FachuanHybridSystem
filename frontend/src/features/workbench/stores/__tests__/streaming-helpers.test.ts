/**
 * Streaming Helpers Tests
 * 测试 SSE 流式消息处理辅助函数
 */

import { reduceStreamingMessage, stripMetadataBlock } from '../streaming-helpers'
import type { StreamingMessage, SSEEvent } from '../../types'

const createStreamingMessage = (overrides: Partial<StreamingMessage> = {}): StreamingMessage => ({
  role: 'assistant',
  content: '',
  toolCalls: [],
  handoffs: [],
  ...overrides,
})

describe('reduceStreamingMessage', () => {
  it('handles meta event - sets model and activeAgent', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'meta', model: 'gpt-4o', agent: 'research' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.model).toBe('gpt-4o')
    expect(result.activeAgent).toBe('research')
    expect(result.currentActivity).toContain('research')
  })

  it('handles activity event with thinking status', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'activity', agent: 'case', status: 'thinking' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.currentActivity).toContain('正在思考')
    expect(result.activeAgent).toBe('case')
  })

  it('handles activity event without thinking status', () => {
    const sm = createStreamingMessage({ currentActivity: 'existing' })
    const event: SSEEvent = { type: 'activity', agent: 'case', status: 'working' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.currentActivity).toBe('existing')
  })

  it('handles delta event - appends content', () => {
    const sm = createStreamingMessage({ content: 'Hello ' })
    const event: SSEEvent = { type: 'delta', content: 'world' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.content).toBe('Hello world')
    expect(result.currentActivity).toBeUndefined()
  })

  it('handles delta event with empty content', () => {
    const sm = createStreamingMessage({ content: 'Hello' })
    const event: SSEEvent = { type: 'delta' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.content).toBe('Hello')
  })

  it('handles tool_call event - adds to toolCalls', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = {
      type: 'tool_call',
      tool_call_id: 'tc-1',
      name: 'search_cases',
      arguments: { q: 'test' },
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls.length).toBe(1)
    expect(result.toolCalls[0].toolCallId).toBe('tc-1')
    expect(result.toolCalls[0].name).toBe('search_cases')
    expect(result.toolCalls[0].status).toBe('running')
    expect(result.currentActivity).toContain('search_cases')
  })

  it('handles tool_call event with tool_name fallback', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = {
      type: 'tool_call',
      tool_call_id: 'tc-1',
      tool_name: 'get_client',
      tool_input: { id: 1 },
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].name).toBe('get_client')
    expect(result.toolCalls[0].arguments).toEqual({ id: 1 })
  })

  it('handles tool_result event - updates matching tool call', () => {
    const sm = createStreamingMessage({
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'running' },
      ],
    })
    const event: SSEEvent = {
      type: 'tool_result',
      tool_call_id: 'tc-1',
      result: { data: [1, 2, 3] },
      success: true,
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].status).toBe('success')
    expect(result.toolCalls[0].success).toBe(true)
    expect(result.currentActivity).toBeUndefined()
  })

  it('handles tool_result event with failure', () => {
    const sm = createStreamingMessage({
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'running' },
      ],
    })
    const event: SSEEvent = {
      type: 'tool_result',
      tool_call_id: 'tc-1',
      result: 'Error occurred',
      success: false,
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].status).toBe('error')
  })

  it('handles handoff event', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = {
      type: 'handoff',
      from_agent: 'triage',
      to_agent: 'research',
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.handoffs.length).toBe(1)
    expect(result.handoffs[0]).toEqual({ from: 'triage', to: 'research' })
    expect(result.currentActivity).toContain('research')
  })

  it('handles error event', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'error', message: 'Connection lost' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.error).toBe('Connection lost')
  })

  it('handles error event without message', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'error' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.error).toBe('未知错误')
  })

  it('returns same reference for unknown event type', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'unknown_type' }
    const result = reduceStreamingMessage(sm, event)
    expect(result).toBe(sm)
  })

  it('preserves existing fields when handling meta event', () => {
    const sm = createStreamingMessage({ content: 'existing', error: 'old error' })
    const event: SSEEvent = { type: 'meta', model: 'gpt-4' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.content).toBe('existing')
    expect(result.error).toBe('old error')
    expect(result.model).toBe('gpt-4')
  })
})

describe('stripMetadataBlock', () => {
  it('removes metadata block wrapped in code fence', () => {
    const text = '分析正文\n\n```\n【案例元数据汇总】\n案号: (2024)京0101民初12345号\n```'
    const result = stripMetadataBlock(text)
    expect(result).toBe('分析正文')
    expect(result).not.toContain('案例元数据汇总')
  })

  it('removes metadata block without code fence', () => {
    const text = '分析正文\n\n【案例元数据汇总】\n案号: (2024)京0101民初12345号'
    const result = stripMetadataBlock(text)
    expect(result).toBe('分析正文')
  })

  it('returns unchanged text when no metadata block', () => {
    const text = 'This is regular content without metadata'
    expect(stripMetadataBlock(text)).toBe(text)
  })

  it('handles empty string', () => {
    expect(stripMetadataBlock('')).toBe('')
  })

  it('trims whitespace after removal', () => {
    const text = '正文  \n\n  【案例元数据汇总】\n数据\n'
    const result = stripMetadataBlock(text)
    expect(result).toBe('正文')
  })
})
