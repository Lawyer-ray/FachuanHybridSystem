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

  it('handles meta event - uses existing activeAgent when agent not provided', () => {
    const sm = createStreamingMessage({ activeAgent: 'contract' })
    const event: SSEEvent = { type: 'meta', model: 'gpt-4o' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.activeAgent).toBe('contract')
    expect(result.model).toBe('gpt-4o')
  })

  it('handles activity event with no agent', () => {
    const sm = createStreamingMessage({ activeAgent: 'case' })
    const event: SSEEvent = { type: 'activity', status: 'thinking' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.currentActivity).toContain('case')
  })

  it('handles tool_call with no name fields', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'tool_call', tool_call_id: 'tc-2' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].name).toBe('')
    expect(result.currentActivity).toContain('工具')
  })

  it('handles tool_result with undefined tool_output', () => {
    const sm = createStreamingMessage({
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'running' },
      ],
    })
    const event: SSEEvent = {
      type: 'tool_result',
      tool_call_id: 'tc-1',
      success: true,
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].status).toBe('success')
  })

  it('handles tool_result with tool_output fallback', () => {
    const sm = createStreamingMessage({
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'running' },
      ],
    })
    const event: SSEEvent = {
      type: 'tool_result',
      tool_call_id: 'tc-1',
      tool_output: { data: [4, 5, 6] },
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].result).toEqual({ data: [4, 5, 6] })
  })

  it('handles handoff with empty agents', () => {
    const sm = createStreamingMessage()
    const event: SSEEvent = { type: 'handoff' }
    const result = reduceStreamingMessage(sm, event)
    expect(result.handoffs[0]).toEqual({ from: '', to: '' })
    expect(result.currentActivity).toContain('助手')
  })

  it('handles tool_result for non-matching toolCallId', () => {
    const sm = createStreamingMessage({
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'running' },
      ],
    })
    const event: SSEEvent = {
      type: 'tool_result',
      tool_call_id: 'tc-2',
      result: 'data',
      success: true,
    }
    const result = reduceStreamingMessage(sm, event)
    expect(result.toolCalls[0].status).toBe('running')
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

describe('connectAndReadStream', () => {
  const createMockReader = (chunks: string[]) => {
    let index = 0
    return {
      read: vi.fn().mockImplementation(() => {
        if (index >= chunks.length) {
          return Promise.resolve({ done: true, value: undefined })
        }
        const chunk = chunks[index++]
        const encoder = new TextEncoder()
        return Promise.resolve({ done: false, value: encoder.encode(chunk) })
      }),
    }
  }

  it('processes SSE data events', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {"type":"delta","content":"hello"}\n\n',
      'data: {"type":"delta","content":" world"}\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream(
      'http://test.com/sse',
      { 'Content-Type': 'application/json' },
      { content: 'test' },
      undefined,
      onEvent,
      onLastEventId,
    )

    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenCalledWith({ type: 'delta', content: 'hello' })
    expect(onEvent).toHaveBeenCalledWith({ type: 'delta', content: ' world' })
  })

  it('skips [DONE] marker', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {"type":"delta","content":"text"}\n\n',
      'data: [DONE]\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('handles meta event with session_id via onLastEventId', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {"type":"meta","session_id":"sess-123"}\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onLastEventId).toHaveBeenCalledWith('sess-123')
  })

  it('skips malformed JSON lines', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {invalid json}\n\n',
      'data: {"type":"delta","content":"ok"}\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ type: 'delta', content: 'ok' })
  })

  it('throws when response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await expect(
      connectAndReadStream('http://test.com/sse', {}, undefined, undefined, vi.fn(), vi.fn()),
    ).rejects.toThrow('HTTP 500')
  })

  it('throws when no reader available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: null,
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await expect(
      connectAndReadStream('http://test.com/sse', {}, undefined, undefined, vi.fn(), vi.fn()),
    ).rejects.toThrow('No reader')
  })

  it('skips non-data lines', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'event: message\n',
      'id: 1\n',
      'retry: 5000\n',
      'data: {"type":"delta","content":"ok"}\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('sends resume_from header when provided', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([])

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    })
    vi.stubGlobal('fetch', fetchMock)

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream(
      'http://test.com/sse',
      { 'Content-Type': 'application/json', 'Last-Event-ID': 'last-id' },
      undefined,
      undefined,
      onEvent,
      onLastEventId,
    )

    expect(fetchMock).toHaveBeenCalledWith('http://test.com/sse', expect.objectContaining({
      headers: expect.objectContaining({ 'Last-Event-ID': 'last-id' }),
    }))
  })

  it('handles empty buffer at end of stream', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {"type":"delta","content":"text"}\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onEvent).toHaveBeenCalledWith({ type: 'delta', content: 'text' })
  })

  it('handles meta event without session_id', async () => {
    const onEvent = vi.fn()
    const onLastEventId = vi.fn()
    const reader = createMockReader([
      'data: {"type":"meta","model":"gpt-4o"}\n\n',
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    const { connectAndReadStream } = await import('../streaming-helpers')
    await connectAndReadStream('http://test.com/sse', {}, undefined, undefined, onEvent, onLastEventId)
    expect(onLastEventId).not.toHaveBeenCalled()
    expect(onEvent).toHaveBeenCalledWith({ type: 'meta', model: 'gpt-4o' })
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
