import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import type { AgentHistoryMessage, AgentSession } from './types'

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
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

describe('copilot store：发送与流式转录', () => {
  it('无会话时先创建，delta 累加进助手气泡，done 收尾', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"你好"}\n\n',
        'data: {"type":"delta","content":"，世界"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('打个招呼')

    expect(copilotApi.createSession).toHaveBeenCalledOnce()
    expect(useCopilot.getState().sessionId).toBe('s-1')
    const { messages, streaming } = useCopilot.getState()
    expect(messages.map((m) => `${m.role}:${m.content}`)).toEqual(['user:打个招呼', 'assistant:你好，世界'])
    expect(streaming).toBe(false)
    expect(messages[1]?.streaming).toBeFalsy()
  })

  it('tool_call/tool_result 归并为工具行，approval_request 进审批卡', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"tool_call","tool_call_id":"t1","name":"mcp__fachuan__list_cases"}\n\n',
        'data: {"type":"tool_result","tool_call_id":"t1","name":"list_cases","result":"[]"}\n\n',
        'data: {"type":"approval_request","approval_id":"a1","tool_name":"mcp__fachuan__delete_case","message":"即将执行高风险操作"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('查案件')

    const { messages, approvals } = useCopilot.getState()
    const tool = messages.find((m) => m.role === 'tool')
    expect(tool?.toolCallId).toBe('t1')
    expect(tool?.content).toBe('[]')
    expect(approvals).toHaveLength(1)
    expect(approvals[0]?.approvalId).toBe('a1')
  })

  it('error 事件置错误提示并收尾助手气泡', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"delta","content":"半截"}\n\n', 'data: {"type":"error","message":"pi 运行失败"}\n\n']),
    )

    await useCopilot.getState().send('x')

    const { lastError, streaming } = useCopilot.getState()
    expect(lastError).toBe('pi 运行失败')
    expect(streaming).toBe(false)
  })

  it('stop 中断流后重拉历史对齐（服务端落库部分回答）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    const history: AgentHistoryMessage[] = [
      { message_id: 1, role: 'user', content: 'x', tool_name: '', created_at: '', metadata: {} },
      { message_id: 2, role: 'assistant', content: '半截', tool_name: '', created_at: '', metadata: { truncated: true } },
    ]
    const fetchHistory = vi.mocked(copilotApi.fetchHistory).mockResolvedValue(history)

    // mock 的流必须响应 abort 信号：真实 fetch 中断时 reader.read() 会以
    // AbortError reject，这里用 controller.error 等价模拟，才能走到 catch 分支
    vi.mocked(copilotApi.openMessageStream).mockImplementation(async (_s, _m, signal) => {
      let controller!: ReadableStreamDefaultController<Uint8Array>
      const abort = () => controller.error(new DOMException('Aborted', 'AbortError'))
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          controller = c
          c.enqueue(encoder.encode('data: {"type":"delta","content":"半"}\n\n'))
          if (signal.aborted) abort()
          else signal.addEventListener('abort', abort)
        },
      })
      return new Response(body, { status: 200 })
    })

    const sending = useCopilot.getState().send('x')
    await vi.waitFor(() => expect(useCopilot.getState().streaming).toBe(true))
    useCopilot.getState().stop()
    await sending

    expect(fetchHistory).toHaveBeenCalledWith('s-1')
    const { messages, streaming } = useCopilot.getState()
    expect(messages[1]?.content).toBe('半截')
    expect(messages[1]?.truncated).toBe(true)
    expect(streaming).toBe(false)
  })

  it('decide 本地即时标记审批终态', async () => {
    vi.mocked(copilotApi.decideApproval).mockResolvedValue({})
    useCopilot.setState({
      approvals: [
        { approvalId: 'a1', toolName: 't', toolArgs: {}, message: 'm', receivedAt: Date.now() },
      ],
    })

    await useCopilot.getState().decide('a1', true)
    expect(useCopilot.getState().approvals[0]?.decided).toBe('approved')
    expect(copilotApi.decideApproval).toHaveBeenCalledWith('a1', true)
  })
})
