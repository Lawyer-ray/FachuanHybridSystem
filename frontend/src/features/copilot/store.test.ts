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
        'data: {"type":"usage","output_tokens":7,"input_tokens":120}\n\n',
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
    // 轮次统计：估算采样在滚、usage 精确值收到、done 收尾
    const { turnStats } = useCopilot.getState()
    expect(turnStats.estTokens).toBeGreaterThan(0)
    expect(turnStats.samples.length).toBeGreaterThanOrEqual(2)
    expect(turnStats.firstDeltaAt).not.toBeNull()
    expect(turnStats.exactTokens).toBe(7)
    expect(turnStats.doneAt).not.toBeNull()
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

  it('审批确认后停止按钮仍能真正中断流（controller 不得被提前置空）', async () => {
    // 回归 2026-10 审查 F1：controller 是模块级单例，decide() 不碰它，
    // 但若任一路径在流未结束时把它置空，stop() 就成 no-op，
    // streaming 永远为 true，Composer 永远停在「停止」态
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.decideApproval).mockResolvedValue({})
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])

    let aborted = false
    vi.mocked(copilotApi.openMessageStream).mockImplementation(async (_s, _m, signal) => {
      let ctrl!: ReadableStreamDefaultController<Uint8Array>
      const abort = () => {
        aborted = true
        ctrl.error(new DOMException('Aborted', 'AbortError'))
      }
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          ctrl = c
          c.enqueue(
            encoder.encode(
              'data: {"type":"approval_request","approval_id":"a1","tool_name":"t","tool_args":{},"message":"m"}\n\n',
            ),
          )
          if (signal.aborted) abort()
          else signal.addEventListener('abort', abort)
        },
      })
      return new Response(body, { status: 200 })
    })

    const sending = useCopilot.getState().send('x')
    await vi.waitFor(() => expect(useCopilot.getState().approvals.length).toBe(1))

    // 用户确认审批（此时流仍在进行）
    await useCopilot.getState().decide('a1', true)

    // 再点停止：必须真中断
    useCopilot.getState().stop()
    await sending

    expect(aborted).toBe(true)
    expect(useCopilot.getState().streaming).toBe(false)
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

  it('createSession 在途时切会话：不得把消息写进用户已切到的会话', async () => {
    // 回归 2026-10 审查 F2：send() 未记录本次发送属于哪个会话，
    // createSession 晚到会覆盖用户刚选中的会话并把消息推进去
    let resolveCreate: (v: AgentSession) => void = () => {}
    vi.mocked(copilotApi.createSession).mockReturnValue(
      new Promise<AgentSession>((res) => {
        resolveCreate = res
      }),
    )
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"done"}\n\n']),
    )

    // 用户在空面板发消息（sessionId 为 null，正在 createSession）
    const pending = useCopilot.getState().send('你好')

    // 在 createSession 返回前，用户切到一个已有会话
    await useCopilot.getState().switchSession('s-existing')
    expect(useCopilot.getState().sessionId).toBe('s-existing')

    // createSession 迟到返回
    resolveCreate(session)
    await pending

    // 用户选择的会话必须保持不变，不得被迟到结果覆盖
    expect(useCopilot.getState().sessionId).toBe('s-existing')
    // 消息不得被推进用户未选择的会话
    expect(useCopilot.getState().messages).toEqual([])
  })
})

describe('copilot store：会话切换竞态', () => {
  it('A→B→A 快速切换后 loadingHistory 不得永久为 true', async () => {
    // 回归 2026-10 审查 F3：过期分支跳过回填时也未清 loadingHistory
    let resolveA1: (v: AgentHistoryMessage[]) => void = () => {}
    vi.mocked(copilotApi.fetchHistory)
      .mockReturnValueOnce(new Promise<AgentHistoryMessage[]>((r) => { resolveA1 = r }))
      .mockResolvedValue([])

    const first = useCopilot.getState().switchSession('A')
    await useCopilot.getState().switchSession('B')
    await useCopilot.getState().switchSession('A')
    // 第一次 A 的请求迟到返回
    resolveA1([])
    await first

    expect(useCopilot.getState().loadingHistory).toBe(false)
    expect(useCopilot.getState().sessionId).toBe('A')
  })
})

// ============ switchSession / withViewTransition 分支（覆盖率补测） ============

describe('copilot store：switchSession 分支', () => {
  it('同会话且非流式：直接返回，不重复拉历史', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false, messages: [{ id: '1', role: 'user', content: 'x' }] })
    await useCopilot.getState().switchSession('s-1')
    expect(copilotApi.fetchHistory).not.toHaveBeenCalled()
  })

  it('同会话但流式中：放行（stop 后重拉）', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ sessionId: 's-1', streaming: true, messages: [] })

    await useCopilot.getState().switchSession('s-1')
    expect(copilotApi.fetchHistory).toHaveBeenCalledWith('s-1')
  })

  it('切到 null：清空消息且不拉历史', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ sessionId: 's-1', streaming: false, messages: [{ id: '1', role: 'user', content: 'x' }] })

    await useCopilot.getState().switchSession(null)
    expect(useCopilot.getState().sessionId).toBeNull()
    expect(useCopilot.getState().messages).toEqual([])
    expect(copilotApi.fetchHistory).not.toHaveBeenCalled()
  })

  it('切会话时会先 stop 在途流', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ sessionId: 's-1', streaming: false, messages: [] })

    await useCopilot.getState().switchSession('s-2')
    // stop 是 no-op（无 controller）也不应抛错
    expect(useCopilot.getState().sessionId).toBe('s-2')
  })

  it('拉历史失败：置错误文案并复位 loadingHistory', async () => {
    vi.mocked(copilotApi.fetchHistory).mockRejectedValue(new Error('boom'))
    useCopilot.setState({ sessionId: null, streaming: false, messages: [] })

    await useCopilot.getState().switchSession('s-3')
    expect(useCopilot.getState().lastError).toBe('加载会话历史失败')
    expect(useCopilot.getState().loadingHistory).toBe(false)
  })

  it('等待期间又切走：迟到结果不回填', async () => {
    let resolveHist: (v: AgentHistoryMessage[]) => void = () => {}
    vi.mocked(copilotApi.fetchHistory).mockReturnValue(
      new Promise<AgentHistoryMessage[]>((r) => {
        resolveHist = r
      }),
    )
    useCopilot.setState({ sessionId: null, streaming: false, messages: [] })

    const pending = useCopilot.getState().switchSession('s-A')
    // 期间切到 B
    useCopilot.setState({ sessionId: 's-B' })
    resolveHist([{ message_id: 1, role: 'user', content: '旧会话', tool_name: '', created_at: '', metadata: {} }])
    await pending

    // 仍是 B，且消息未被 A 的历史覆盖
    expect(useCopilot.getState().sessionId).toBe('s-B')
    expect(useCopilot.getState().messages).toEqual([])
  })
})
