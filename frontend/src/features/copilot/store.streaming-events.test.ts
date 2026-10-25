import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import type { AgentSession } from './types'

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
}))

const encoder = new TextEncoder()

/** 把一组 SSE 帧包成真实 Response（body 为 ReadableStream） */
function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

const session: AgentSession = {
  session_id: 's-1',
  title: '',
  status: 'active',
  llm_model: '',
  created_at: '',
  updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

describe('copilot store：流式事件处理', () => {
  it('thinking 增量累积到 thinking 字段，不计入正文', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"thinking","content":"思考A"}\n\n',
        'data: {"type":"thinking","content":"思考B"}\n\n',
        'data: {"type":"delta","content":"正文"}\n\n',
        'data: {"type":"done"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')
    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.content).toBe('正文')
    expect(assistant.thinking).toBe('思考A思考B')
    // 首个正文 delta 到达后 thinkingDone 置位
    expect(assistant.thinkingDone).toBe(true)
  })

  it('只有 thinking 没有正文：thinkingDone 保持未置位', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"thinking","content":"仅思考"}\n\n', 'data: {"type":"done"}\n\n']),
    )

    await useCopilot.getState().send('x')
    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.thinking).toBe('仅思考')
    expect(assistant.thinkingDone).toBeFalsy()
  })

  it('HTTP 非 2xx：进错误态并提示连接中断', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      new Response(null, { status: 500 }),
    )

    await useCopilot.getState().send('x')
    expect(useCopilot.getState().lastError).toBe('连接中断，请重试')
    expect(useCopilot.getState().streaming).toBe(false)
  })

  it('响应无 body：同样进错误态', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue({
      ok: true,
      body: null,
      status: 200,
    } as unknown as Response)

    await useCopilot.getState().send('x')
    expect(useCopilot.getState().lastError).toBe('连接中断，请重试')
  })

  it('空文本或流式中重复发送：直接返回不建会话', async () => {
    const createSpy = vi.mocked(copilotApi.createSession)
    await useCopilot.getState().send('   ')
    expect(createSpy).not.toHaveBeenCalled()

    useCopilot.setState({ streaming: true })
    await useCopilot.getState().send('有内容')
    expect(createSpy).not.toHaveBeenCalled()
    useCopilot.setState({ streaming: false })
  })

  it('创建会话失败：给错误提示且不进入流式', async () => {
    vi.mocked(copilotApi.createSession).mockRejectedValue(new Error('boom'))

    await useCopilot.getState().send('x')
    expect(useCopilot.getState().lastError).toBe('创建会话失败，请稍后重试')
    expect(useCopilot.getState().streaming).toBe(false)
  })

  it('畸形帧被跳过，不影响后续正常帧', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: 不是JSON\n\n',
        'data: {"type":"unknown_type","x":1}\n\n',
        'data: {"type":"delta","content":"正常"}\n\n',
        'data: {"type":"done"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')
    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.content).toBe('正常')
  })

  it('error 事件：置 lastError 并收尾', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"error","message":"服务端拒绝"}\n\n']),
    )

    await useCopilot.getState().send('x')
    expect(useCopilot.getState().lastError).toBe('服务端拒绝')
    expect(useCopilot.getState().streaming).toBe(false)
  })
})

// ============ 排队可见 / 插话 / 后台任务 / 离线审批（P0 批次） ============

describe('copilot store：排队可见', () => {
  it('queued 事件设置名次，首个推进事件清除', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"activity","status":"queued","position":3}\n\n',
        'data: {"type":"delta","content":"开始"}\n\n',
        'data: {"type":"done"}\n\n',
      ]),
    )

    const sending = useCopilot.getState().send('x')
    // 流式期间无法中途断言（同步消费），改从结果验证：结束后的 queuePosition 必为 null
    await sending
    expect(useCopilot.getState().queuePosition).toBeNull()
    expect(useCopilot.getState().messages.find((m) => m.role === 'assistant')?.content).toBe('开始')
  })

  it('非 queued 的 activity（thinking）不设 queuePosition', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"activity","status":"thinking"}\n\n', 'data: {"type":"done"}\n\n']),
    )
    await useCopilot.getState().send('x')
    expect(useCopilot.getState().queuePosition).toBeNull()
  })
})

describe('copilot store：断线后历史对齐', () => {
  it('HTTP 非 2xx：同样重拉历史（不只主动停止才拉）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    const fetchHistory = vi.mocked(copilotApi.fetchHistory).mockResolvedValue([
      { message_id: 1, role: 'user', content: 'x', tool_name: '', created_at: '', metadata: {} },
      { message_id: 2, role: 'assistant', content: '半截', tool_name: '', created_at: '', metadata: { truncated: true } },
    ])
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(new Response(null, { status: 500 }))

    await useCopilot.getState().send('x')

    expect(fetchHistory).toHaveBeenCalledWith('s-1')
    // 服务端落库的部分回答被恢复，而不是白屏
    expect(useCopilot.getState().messages[1]?.content).toBe('半截')
    expect(useCopilot.getState().lastError).toBe('连接中断，请重试')
  })
})

describe('copilot store：refreshHistory', () => {
  it('非流式时重拉并替换转录', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([
      { message_id: 3, role: 'assistant', content: '【后台任务完成】已生成回答', tool_name: '', created_at: '', metadata: {} },
    ])
    useCopilot.setState({ sessionId: 't-9', streaming: false, messages: [] })

    await useCopilot.getState().refreshHistory()
    expect(useCopilot.getState().messages[0]?.content).toContain('后台任务完成')
  })

  it('流式中跳过（避免与实时追加冲突）', async () => {
    const fetchHistory = vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ sessionId: 't-9', streaming: true })

    await useCopilot.getState().refreshHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
    useCopilot.setState({ streaming: false })
  })
})

// ============ 业务内会话（案件/合同页打开，P1-1） ============

describe('copilot store：上下文水位与压缩事件', () => {
  it('done 带水位字段时写入 contextUsage；不带时保持原值', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"答"}\n\n',
        'data: {"type":"done","session_id":"s-1","context_used_tokens":65536,"context_total_tokens":131072}\n\n',
      ]),
    )
    await useCopilot.getState().send('x')
    expect(useCopilot.getState().contextUsage).toEqual({ used: 65536, total: 131072 })

    // 第二轮 done 不带水位（旧后端）：不把已知水位冲掉
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"答"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )
    await useCopilot.getState().send('y')
    expect(useCopilot.getState().contextUsage).toEqual({ used: 65536, total: 131072 })
  })

  it('compaction start/end 切换 compacting 状态', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"compaction","phase":"start"}\n\n',
        'data: {"type":"delta","content":"答"}\n\n',
        'data: {"type":"compaction","phase":"end"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )
    await useCopilot.getState().send('x')
    expect(useCopilot.getState().compacting).toBe(false)
  })
})
