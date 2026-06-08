/**
 * Message Factory Tests
 * 测试工作台消息工厂函数
 */

import {
  createUserMessage,
  finalizeStreamingMessages,
  createAbortedMessage,
  createPartialMessage,
  createErrorMessage,
  createBatchItemMessage,
  createBatchSummaryMessage,
} from '../message-factory'
import type { StreamingMessage } from '../../types'

describe('createUserMessage', () => {
  it('creates message with user role', () => {
    const msg = createUserMessage('Hello')
    expect(msg.role).toBe('user')
    expect(msg.content).toBe('Hello')
  })

  it('has empty default fields', () => {
    const msg = createUserMessage('test')
    expect(msg.llm_model).toBe('')
    expect(msg.tool_call_id).toBe('')
    expect(msg.tool_name).toBe('')
    expect(msg.tool_input).toEqual({})
    expect(msg.tool_output).toEqual({})
    expect(msg.metadata).toEqual({})
  })

  it('sets id as a number', () => {
    const msg = createUserMessage('test')
    expect(typeof msg.id).toBe('number')
  })

  it('sets created_at as ISO string', () => {
    const msg = createUserMessage('test')
    expect(() => new Date(msg.created_at)).not.toThrow()
  })
})

describe('finalizeStreamingMessages', () => {
  it('returns empty array for null', () => {
    expect(finalizeStreamingMessages(null)).toEqual([])
  })

  it('creates assistant message from content', () => {
    const streaming: StreamingMessage = {
      role: 'assistant',
      content: 'Hello from assistant',
      toolCalls: [],
      handoffs: [],
      model: 'gpt-4o',
    }
    const messages = finalizeStreamingMessages(streaming)
    expect(messages.length).toBe(1)
    expect(messages[0].role).toBe('assistant')
    expect(messages[0].content).toBe('Hello from assistant')
    expect(messages[0].llm_model).toBe('gpt-4o')
  })

  it('creates tool messages from toolCalls', () => {
    const streaming: StreamingMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search_cases', arguments: { q: 'test' }, status: 'success', result: { data: [] }, success: true },
      ],
      handoffs: [],
    }
    const messages = finalizeStreamingMessages(streaming)
    const toolMsg = messages.find((m) => m.role === 'tool')
    expect(toolMsg).toBeDefined()
    expect(toolMsg?.tool_name).toBe('search_cases')
    expect(toolMsg?.tool_call_id).toBe('tc-1')
    expect(toolMsg?.metadata.success).toBe(true)
  })

  it('creates both tool and assistant messages', () => {
    const streaming: StreamingMessage = {
      role: 'assistant',
      content: 'Done',
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'success' },
      ],
      handoffs: [],
    }
    const messages = finalizeStreamingMessages(streaming)
    expect(messages.length).toBe(2)
    expect(messages[0].role).toBe('tool')
    expect(messages[1].role).toBe('assistant')
  })

  it('handles tool calls with error status', () => {
    const streaming: StreamingMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [
        { toolCallId: 'tc-1', name: 'search', arguments: {}, status: 'error', success: false },
      ],
      handoffs: [],
    }
    const messages = finalizeStreamingMessages(streaming)
    expect(messages[0].metadata.success).toBe(false)
  })

  it('skips assistant message when content is empty and no tool calls', () => {
    const streaming: StreamingMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [],
      handoffs: [],
    }
    const messages = finalizeStreamingMessages(streaming)
    expect(messages.length).toBe(0)
  })
})

describe('createAbortedMessage', () => {
  it('appends [已中断] to content', () => {
    const msg = createAbortedMessage('Partial response')
    expect(msg.content).toContain('Partial response')
    expect(msg.content).toContain('[已中断]')
  })

  it('sets aborted metadata', () => {
    const msg = createAbortedMessage('test')
    expect(msg.metadata.aborted).toBe(true)
  })

  it('sets assistant role', () => {
    const msg = createAbortedMessage('test')
    expect(msg.role).toBe('assistant')
  })

  it('includes model when provided', () => {
    const msg = createAbortedMessage('test', 'gpt-4o')
    expect(msg.llm_model).toBe('gpt-4o')
  })
})

describe('createPartialMessage', () => {
  it('appends connection loss notice', () => {
    const msg = createPartialMessage('Partial')
    expect(msg.content).toContain('[连接中断，部分内容已保留]')
  })

  it('sets partial metadata', () => {
    const msg = createPartialMessage('test')
    expect(msg.metadata.partial).toBe(true)
  })

  it('uses provided model', () => {
    const msg = createPartialMessage('test', 'gpt-4')
    expect(msg.llm_model).toBe('gpt-4')
  })
})

describe('createErrorMessage', () => {
  it('includes error message in content', () => {
    const msg = createErrorMessage('Network timeout')
    expect(msg.content).toContain('请求失败: Network timeout')
  })

  it('uses assistant role', () => {
    const msg = createErrorMessage('error')
    expect(msg.role).toBe('assistant')
  })
})

describe('createBatchItemMessage', () => {
  it('includes file name as heading', () => {
    const msg = createBatchItemMessage('doc.pdf', 'Content here', 'job-1')
    expect(msg.content).toContain('### doc.pdf')
    expect(msg.content).toContain('Content here')
  })

  it('sets batch_item metadata', () => {
    const msg = createBatchItemMessage('doc.pdf', 'content', 'job-1')
    expect(msg.metadata.source).toBe('batch_item')
    expect(msg.metadata.job_id).toBe('job-1')
  })
})

describe('createBatchSummaryMessage', () => {
  it('uses summary as content', () => {
    const msg = createBatchSummaryMessage('Summary text', 'job-1')
    expect(msg.content).toBe('Summary text')
  })

  it('sets batch_analysis metadata', () => {
    const msg = createBatchSummaryMessage('summary', 'job-1')
    expect(msg.metadata.source).toBe('batch_analysis')
    expect(msg.metadata.job_id).toBe('job-1')
  })
})
