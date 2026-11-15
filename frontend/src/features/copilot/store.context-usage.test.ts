/**
 * copilot store 的上下文水位与消息反馈 slice 测试（node 环境）。
 *
 * 这一片全是「增强信息」：水位拉不到、压缩失败、点赞失败，都不该让一次对话
 * 停下来。但它又直接决定律师看到什么，所以三件事必须逐条守住：
 * - 水位**只回填仍是当前会话**的那一份：切会话后才回来的旧响应若写进去，
 *   新会话的水位会显示成上一个会话的数字，律师据此判断「还能不能继续问」；
 * - 压缩有并发闸门（`compacting` / `streaming`）：流式期间压缩会把正在生成
 *   的回答一起压掉；
 * - 点赞/点踩是乐观更新 + 失败回滚：不回滚会让界面永远显示一个后端没存下的评价。
 */
import { HTTPError } from 'ky'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import type { AgentCompactReceipt, AgentSessionStats, ChatMessage } from './types'

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
  fetchSessionStats: vi.fn(),
  compactSession: vi.fn(),
  rateMessage: vi.fn(),
}))

function stats(used: number | null, total: number | null): AgentSessionStats {
  return {
    output_tokens: 0,
    input_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    context_used_tokens: used,
    context_total_tokens: total,
    context_percent: used != null && total ? used / total : null,
  }
}

function compacted(used: number | null, total: number | null): AgentCompactReceipt {
  return { compacted: true, context_used_tokens: used, context_total_tokens: total }
}

/** 「db-<id>」是历史消息的 id 约定：打分按它反查本地那条 */
function assistant(id: string, rating?: 'up' | 'down'): ChatMessage {
  return { id, role: 'assistant', content: '答', rating }
}

/** ky 的 HTTPError 需要一个 Response；这里只需要 status */
function httpError(status: number): HTTPError {
  return new HTTPError(new Response(null, { status }), new Request('http://localhost/x'), {} as never)
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

describe('setContextUsage / refreshContextUsage', () => {
  it('setContextUsage 直接写入水位', () => {
    useCopilot.getState().setContextUsage(1000, 8000)
    expect(useCopilot.getState().contextUsage).toEqual({ used: 1000, total: 8000 })
  })

  it('没有会话时不发请求（新对话还没有 stats 端点可打）', async () => {
    await useCopilot.getState().refreshContextUsage()
    expect(copilotApi.fetchSessionStats).not.toHaveBeenCalled()
  })

  it('有会话时回填上下文水位', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.fetchSessionStats).mockResolvedValue(stats(3000, 12000))

    await useCopilot.getState().refreshContextUsage()

    expect(copilotApi.fetchSessionStats).toHaveBeenCalledWith('s-1')
    expect(useCopilot.getState().contextUsage).toEqual({ used: 3000, total: 12000 })
  })

  it('等待期间切走会话 → 不回填（否则新会话显示上一个会话的水位）', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    let resolveStats: ((v: AgentSessionStats) => void) | null = null
    vi.mocked(copilotApi.fetchSessionStats).mockImplementation(
      () => new Promise<AgentSessionStats>((resolve) => {
        resolveStats = resolve
      }),
    )

    const pending = useCopilot.getState().refreshContextUsage()
    useCopilot.setState({ sessionId: 's-2' })
    resolveStats!(stats(9999, 10000))
    await pending

    expect(useCopilot.getState().contextUsage).toEqual({ used: null, total: null })
  })

  it('拉取失败静默：水位是增强信息，不该给律师弹错', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.fetchSessionStats).mockRejectedValue(new Error('503'))

    await expect(useCopilot.getState().refreshContextUsage()).resolves.toBeUndefined()
    expect(useCopilot.getState().lastError).toBeNull()
  })
})

describe('compactContext：手动压缩上下文', () => {
  it('没有会话时什么都不做', async () => {
    await useCopilot.getState().compactContext()
    expect(copilotApi.compactSession).not.toHaveBeenCalled()
  })

  it('已在压缩时重入被拦下（连点两下不该压两次）', async () => {
    useCopilot.setState({ sessionId: 's-1', compacting: true })
    await useCopilot.getState().compactContext()
    expect(copilotApi.compactSession).not.toHaveBeenCalled()
  })

  it('流式生成中不压缩（会把正在生成的回答一起压掉）', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: true })
    await useCopilot.getState().compactContext()
    expect(copilotApi.compactSession).not.toHaveBeenCalled()
  })

  it('压缩成功：回填新水位，compacting 复位', async () => {
    useCopilot.setState({ sessionId: 's-1', lastError: '上一次的错' })
    vi.mocked(copilotApi.compactSession).mockResolvedValue(compacted(500, 12000))

    await useCopilot.getState().compactContext()

    expect(useCopilot.getState().contextUsage).toEqual({ used: 500, total: 12000 })
    expect(useCopilot.getState().compacting).toBe(false)
    // 重试成功后清掉旧错误，否则界面一直挂着一条已解决的报错
    expect(useCopilot.getState().lastError).toBeNull()
  })

  it('后端说没东西可压（compacted=false）→ 说明原因，不当成失败', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.compactSession).mockResolvedValue({ ...compacted(0, 12000), compacted: false })

    await useCopilot.getState().compactContext()

    expect(useCopilot.getState().lastError).toBe('会话还没有对话历史，无需压缩')
    expect(useCopilot.getState().compacting).toBe(false)
  })

  it('429 单独给「人数较多」的忙提示（让律师等一会再试，而不是以为坏了）', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.compactSession).mockRejectedValue(httpError(429))

    await useCopilot.getState().compactContext()

    expect(useCopilot.getState().lastError).toBe('当前使用人数较多，请稍后再试')
    expect(useCopilot.getState().compacting).toBe(false)
  })

  it('其他失败给通用文案，且 compacting 无论成败都复位', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.compactSession).mockRejectedValue(httpError(500))

    await useCopilot.getState().compactContext()

    expect(useCopilot.getState().lastError).toBe('压缩失败，请稍后再试')
    expect(useCopilot.getState().compacting).toBe(false)
  })

  it('非 HTTP 异常（断网）也走通用文案，不把内部错误抛给用户', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    vi.mocked(copilotApi.compactSession).mockRejectedValue(new TypeError('Failed to fetch'))

    await useCopilot.getState().compactContext()

    expect(useCopilot.getState().lastError).toBe('压缩失败，请稍后再试')
  })
})

describe('rateMessage：点赞 / 点踩 / 撤销', () => {
  it('点赞先本地生效再提交（点下去立刻有反馈）', async () => {
    useCopilot.setState({ messages: [assistant('db-12')] })
    vi.mocked(copilotApi.rateMessage).mockResolvedValue({})

    await useCopilot.getState().rateMessage(12, 'up')

    expect(copilotApi.rateMessage).toHaveBeenCalledWith(12, 'up')
    expect(useCopilot.getState().messages[0]?.rating).toBe('up')
  })

  it('none 是撤销：本地把 rating 清成 undefined', async () => {
    useCopilot.setState({ messages: [assistant('db-12', 'down')] })
    vi.mocked(copilotApi.rateMessage).mockResolvedValue({})

    await useCopilot.getState().rateMessage(12, 'none')

    expect(useCopilot.getState().messages[0]?.rating).toBeUndefined()
  })

  it('提交失败回滚到原值（界面不能永远显示一个后端没存下的评价）', async () => {
    useCopilot.setState({ messages: [assistant('db-12', 'up')] })
    vi.mocked(copilotApi.rateMessage).mockRejectedValue(new Error('500'))

    await useCopilot.getState().rateMessage(12, 'down')

    expect(useCopilot.getState().messages[0]?.rating).toBe('up')
  })

  it('原本没有评价时失败回滚成「没有评价」，不是空字符串', async () => {
    useCopilot.setState({ messages: [assistant('db-12')] })
    vi.mocked(copilotApi.rateMessage).mockRejectedValue(new Error('500'))

    await useCopilot.getState().rateMessage(12, 'down')

    expect(useCopilot.getState().messages[0]?.rating).toBeUndefined()
  })

  it('只改目标那条消息，其他消息不受影响', async () => {
    useCopilot.setState({ messages: [assistant('db-1', 'down'), assistant('db-2')] })
    vi.mocked(copilotApi.rateMessage).mockResolvedValue({})

    await useCopilot.getState().rateMessage(2, 'up')

    const [first, second] = useCopilot.getState().messages
    expect(first?.rating).toBe('down')
    expect(second?.rating).toBe('up')
  })

  it('消息不在本地（非历史消息 id）时不崩，也不凭空造一条', async () => {
    useCopilot.setState({ messages: [assistant('local-1')] })
    vi.mocked(copilotApi.rateMessage).mockResolvedValue({})

    await useCopilot.getState().rateMessage(99, 'up')

    expect(useCopilot.getState().messages).toHaveLength(1)
    expect(useCopilot.getState().messages[0]?.rating).toBeUndefined()
  })
})
