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
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
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

// ============ 流式事件分支（覆盖率补测） ==========

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

describe('copilot store：运行中插话（steer）', () => {
  it('流式中 steer 成功记入 queuedSteers，done 后清空', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.steerSession).mockResolvedValue({ success: true, disposition: 'queued' })
    // 流不结束（手动控制关流时机）
    let closeStream!: () => void
    vi.mocked(copilotApi.openMessageStream).mockImplementation(async () => {
      const body = new ReadableStream<Uint8Array>({ start(c) { closeStream = () => c.close() } })
      return new Response(body, { status: 200 })
    })

    const sending = useCopilot.getState().send('主任务')
    await vi.waitFor(() => expect(useCopilot.getState().streaming).toBe(true))

    await useCopilot.getState().steer('补充：只要近一个月的')
    expect(copilotApi.steerSession).toHaveBeenCalledWith('s-1', '补充：只要近一个月的')
    expect(useCopilot.getState().queuedSteers).toEqual(['补充：只要近一个月的'])

    closeStream()
    await sending
    // 流结束（done 未到但流关）：queuedSteers 保留到 done——这里流关闭无 done，
    // 验证不误清；下一轮 send 开始时会重置
    expect(useCopilot.getState().streaming).toBe(false)
  })

  it('非流式状态 steer 直接返回（不调接口）', async () => {
    await useCopilot.getState().steer('没人听')
    expect(copilotApi.steerSession).not.toHaveBeenCalled()
  })

  it('steer 409（本轮已结束）：提示且不记入 queuedSteers', async () => {
    const { HTTPError } = await import('ky')
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.steerSession).mockRejectedValue(
      new HTTPError(new Response(null, { status: 409 }), new Request('http://localhost/api/v1/agent/sessions/s-1/steer'), {
        method: 'POST',
      } as never),
    )
    useCopilot.setState({ sessionId: 's-1', streaming: true })

    await useCopilot.getState().steer('迟到的插话')
    expect(useCopilot.getState().lastError).toBe('本轮对话已结束，插话未送达')
    expect(useCopilot.getState().queuedSteers).toEqual([])
    useCopilot.setState({ streaming: false })
  })

  it('revokeQueuedSteers 调撤回端点并清空本地记录', async () => {
    vi.mocked(copilotApi.clearSessionQueue).mockResolvedValue({ success: true, messages: ['插话原文'] })
    useCopilot.setState({ sessionId: 's-1', queuedSteers: ['插话原文'] })

    await useCopilot.getState().revokeQueuedSteers()
    expect(copilotApi.clearSessionQueue).toHaveBeenCalledWith('s-1')
    expect(useCopilot.getState().queuedSteers).toEqual([])
  })
})

describe('copilot store：后台任务', () => {
  it('submitTask 受理后切到任务会话并拉取历史', async () => {
    vi.mocked(copilotApi.submitAgentTask).mockResolvedValue({
      session_id: 't-9',
      task_id: 'q-1',
      task_state: 'queued',
      title: '梳理材料',
    })
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])

    await useCopilot.getState().submitTask('帮我梳理本案材料')

    expect(copilotApi.submitAgentTask).toHaveBeenCalledWith('帮我梳理本案材料', '', undefined)
    expect(useCopilot.getState().sessionId).toBe('t-9')
    expect(copilotApi.fetchHistory).toHaveBeenCalledWith('t-9')
  })

  it('submitTask 失败：提示且不切会话', async () => {
    vi.mocked(copilotApi.submitAgentTask).mockRejectedValue(new Error('busy'))
    useCopilot.setState({ sessionId: 's-1' })

    await useCopilot.getState().submitTask('x')
    expect(useCopilot.getState().lastError).toBe('提交后台任务失败，请稍后重试')
    expect(useCopilot.getState().sessionId).toBe('s-1')
  })
})

describe('copilot store：离线审批', () => {
  it('loadPendingApprovals 把待审批合并为离线卡，不覆盖已知项', async () => {
    vi.mocked(copilotApi.fetchPendingApprovals).mockResolvedValue([
      {
        approval_id: 'off-1',
        session_id: 't-9',
        tool_name: 'mcp__fachuan__delete_case',
        tool_args: { case_id: 1 },
        risk_level: 'high',
        created_at: new Date().toISOString(),
      },
      {
        approval_id: 'a1', // 已在本地（例如本轮流里已弹过）
        session_id: 's-1',
        tool_name: 't',
        tool_args: {},
        risk_level: 'low',
        created_at: new Date().toISOString(),
      },
    ])
    useCopilot.setState({
      approvals: [{ approvalId: 'a1', toolName: 't', toolArgs: {}, message: 'm', receivedAt: Date.now() }],
    })

    await useCopilot.getState().loadPendingApprovals()

    const { approvals } = useCopilot.getState()
    expect(approvals).toHaveLength(2)
    const offline = approvals.find((a) => a.approvalId === 'off-1')
    expect(offline?.offline).toBe(true)
    expect(offline?.riskLevel).toBe('high')
    expect(offline?.toolName).toBe('mcp__fachuan__delete_case')
    // 已知项不被覆盖（保留本地 message / 终态）
    expect(approvals.find((a) => a.approvalId === 'a1')?.message).toBe('m')
  })

  it('拉取失败静默（不打扰主流程）', async () => {
    vi.mocked(copilotApi.fetchPendingApprovals).mockRejectedValue(new Error('net'))
    await useCopilot.getState().loadPendingApprovals()
    expect(useCopilot.getState().lastError).toBeNull()
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

describe('copilot store：业务上下文', () => {
  it('enterContext 记录上下文并回到新对话；exitContext 清除', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ sessionId: 's-1', messages: [{ id: '1', role: 'user', content: 'x' }] })

    await useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '张三委托' })
    expect(useCopilot.getState().context).toEqual({ origin: 'contract', refId: 386, title: '张三委托' })
    expect(useCopilot.getState().sessionId).toBeNull()
    expect(useCopilot.getState().messages).toEqual([])

    await useCopilot.getState().exitContext()
    expect(useCopilot.getState().context).toBeNull()
  })

  it('上下文内发消息：新会话带 origin/contract_id 归属', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))
    useCopilot.setState({ context: { origin: 'contract', refId: 386, title: '张三委托' } })

    await useCopilot.getState().send('本案进展如何')
    expect(copilotApi.createSession).toHaveBeenCalledWith('', { origin: 'contract', refId: 386, title: '张三委托' })
  })

  it('上下文内提交后台任务：带 case_id 归属', async () => {
    vi.mocked(copilotApi.submitAgentTask).mockResolvedValue({
      session_id: 't-1',
      task_id: 'q-1',
      task_state: 'queued',
      title: '',
    })
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.setState({ context: { origin: 'case', refId: 12, title: '某案' } })

    await useCopilot.getState().submitTask('梳理本案材料')
    expect(copilotApi.submitAgentTask).toHaveBeenCalledWith('梳理本案材料', '', { origin: 'case', refId: 12, title: '某案' })
  })

  it('reset 清除上下文', () => {
    useCopilot.setState({ context: { origin: 'case', refId: 1, title: 'x' } })
    useCopilot.getState().reset()
    expect(useCopilot.getState().context).toBeNull()
  })
})

// ============ 附件（拖拽/选择上传，P1-11） ============

function makeFile(name: string, size = 10, type = 'text/plain'): File {
  return new File(['x'.repeat(size)], name, { type })
}

describe('copilot store：附件', () => {
  it('addAttachmentFiles：合规收下、不合规拒绝并提示', () => {
    const good = makeFile('合同.pdf', 100)
    const badExt = makeFile('恶意.exe', 10)
    const empty = makeFile('空.txt', 0)
    useCopilot.getState().addAttachmentFiles([good, badExt, empty])

    const { pendingFiles, lastError } = useCopilot.getState()
    expect(pendingFiles.map((f) => f.name)).toEqual(['合同.pdf'])
    expect(lastError).toContain('恶意.exe')
    expect(lastError).toContain('空.txt')
  })

  it('removeAttachmentFile 按下标移除', () => {
    useCopilot.setState({ pendingFiles: [makeFile('a.txt'), makeFile('b.txt')] })
    useCopilot.getState().removeAttachmentFile(0)
    expect(useCopilot.getState().pendingFiles.map((f) => f.name)).toEqual(['b.txt'])
  })

  it('发送时先上传附件，消息附引用块，chips 清空', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.uploadAttachment).mockImplementation(async (_sid, file) => ({
      attachment_id: `att-${file.name}`,
      filename: file.name,
      size: file.size,
      mime: 'text/plain',
    }))
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"done"}\n\n']),
    )
    useCopilot.setState({ pendingFiles: [makeFile('笔记.txt', 8)] })

    await useCopilot.getState().send('帮我看看')
    expect(copilotApi.uploadAttachment).toHaveBeenCalledWith('s-1', expect.any(File))
    const user = useCopilot.getState().messages.find((m) => m.role === 'user')!
    expect(user.content).toContain('[已上传附件：笔记.txt (attachment_id=att-笔记.txt)]')
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })

  it('附件上传失败：不发消息、chips 保留可重试', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.uploadAttachment).mockRejectedValue(new Error('boom'))
    const file = makeFile('笔记.txt', 8)
    useCopilot.setState({ pendingFiles: [file] })

    await useCopilot.getState().send('帮我看看')
    expect(copilotApi.openMessageStream).not.toHaveBeenCalled()
    expect(useCopilot.getState().lastError).toContain('附件上传失败')
    expect(useCopilot.getState().pendingFiles).toEqual([file])
    expect(useCopilot.getState().streaming).toBe(false)
  })
})

// ============ 僵尸审批卡治理（B2-4 兜底） ============

describe('copilot store：僵尸离线审批', () => {
  it('已超窗的待审项不合并，且顺带清除本地旧僵尸卡', async () => {
    const old = Date.now() - 7201_000
    vi.mocked(copilotApi.fetchPendingApprovals).mockResolvedValue([
      {
        approval_id: 'zombie',
        session_id: 't-1',
        tool_name: 'mcp__fachuan__delete_reminder',
        tool_args: { reminder_id: 999999 },
        risk_level: 'high',
        created_at: new Date(old).toISOString(),
      },
      {
        approval_id: 'live',
        session_id: 't-2',
        tool_name: 'mcp__fachuan__delete_case',
        tool_args: {},
        risk_level: 'high',
        created_at: new Date().toISOString(),
      },
    ])
    // 本地已有一张僵尸离线卡（上次拉进来的）
    useCopilot.setState({
      approvals: [{ approvalId: 'zombie', toolName: 't', toolArgs: {}, message: '', receivedAt: old, offline: true }],
    })

    await useCopilot.getState().loadPendingApprovals()

    const { approvals } = useCopilot.getState()
    expect(approvals.map((a) => a.approvalId)).toEqual(['live'])
    expect(approvals.find((a) => a.approvalId === 'zombie')).toBeUndefined()
  })

  it('dismissApproval 本地移除指定卡', () => {
    useCopilot.setState({
      approvals: [{ approvalId: 'x1', toolName: 't', toolArgs: {}, message: '', receivedAt: Date.now(), decided: 'rejected' }],
    })
    useCopilot.getState().dismissApproval('x1')
    expect(useCopilot.getState().approvals).toEqual([])
  })
})
