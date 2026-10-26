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

describe('copilot store：页面感知注入', () => {
  // mockImplementation：每次调用生成全新 Response——Response body 只能读一次，
  // 共享同一个 mock 返回值会让后续 send 复用已耗尽的流、走 catch 清空消息
  const emptyStream = () =>
    vi.mocked(copilotApi.openMessageStream).mockImplementation(() =>
      Promise.resolve(sseResponse(['data: {"type":"done","session_id":"s-1"}\n\n'])),
    )

  it('通用模式：页面变化后首条注入 [当前页面：…] 锚点，本地气泡折叠为 chip', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    const st = useCopilot.getState()
    st.setPageHint('委托详情 · 某银行（contract_id=8）')
    await st.send('总结一下')

    // 出站消息带锚点前缀（模型可拿 contract_id 用工具了解页面）
    const sent = vi.mocked(copilotApi.openMessageStream).mock.calls[0]?.[1] ?? ''
    expect(sent).toBe('[当前页面：委托详情 · 某银行（contract_id=8）]\n总结一下')
    // 本地气泡：锚点折叠成 pageHint 字段、正文干净
    const user = useCopilot.getState().messages[0]!
    expect(user.pageHint).toBe('委托详情 · 某银行（contract_id=8）')
    expect(user.content).toBe('总结一下')
  })

  it('同一页面第二条不重复注入；业务 context 模式每轮注入归属锚点', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    const st = useCopilot.getState()
    st.setPageHint('办案列表页')
    await st.send('第一条')
    await st.send('第二条')
    expect(vi.mocked(copilotApi.openMessageStream).mock.calls[1]?.[1]).toBe('第二条')

    // 业务范围（详情页工作区/浮层 context）：每轮注入归属锚点——pi 的
    // compaction 可能压掉首轮上下文，不重复注入模型就会反问「哪个案件」
    await st.enterContext({ origin: 'contract', refId: 8, title: '某银行' })
    st.setPageHint('委托详情 · 某银行（contract_id=8）')
    await st.send('范围内的消息')
    const last = vi.mocked(copilotApi.openMessageStream).mock.calls[2]?.[1]
    expect(last).toBe('[当前业务：本委托「某银行」 contract_id=8]\n范围内的消息')
    expect(last).not.toContain('当前页面')
    // 本地气泡：归属锚点折叠成 bizHint 字段、正文干净
    const user = useCopilot.getState().messages.at(-2)
    expect(user?.bizHint).toBe('本委托「某银行」 contract_id=8')
    expect(user?.content).toBe('范围内的消息')
  })
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

  it('usage 带 cache 字段时累加进 turnStats（旧格式向后兼容）', async () => {
    // 2026-10-25：后端开始上报 cacheRead/cacheWrite。这是验证「提示词前缀
    // 稳定 → 命中 prompt cache」的唯一手段，前端必须能拿到。
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"好"}\n\n',
        // 一轮内多段 assistant 各报一次，必须累加
        'data: {"type":"usage","output_tokens":5,"input_tokens":100,"cache_read_tokens":800,"cache_write_tokens":50}\n\n',
        'data: {"type":"usage","output_tokens":3,"input_tokens":20,"cache_read_tokens":900,"cache_write_tokens":0}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('查一下')

    const { turnStats } = useCopilot.getState()
    // exactTokens 仍只算输出（用于展示生成速度，混进输入会虚高）
    expect(turnStats.exactTokens).toBe(8)
    expect(turnStats.inputTokens).toBe(120)
    expect(turnStats.cacheReadTokens).toBe(1700)
    expect(turnStats.cacheWriteTokens).toBe(50)
  })

  it('usage 缺 cache 字段时按 0 处理（旧后端/某些 provider 不上报）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"好"}\n\n',
        'data: {"type":"usage","output_tokens":7,"input_tokens":120}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('打个招呼')

    const { turnStats } = useCopilot.getState()
    expect(turnStats.exactTokens).toBe(7)
    expect(turnStats.inputTokens).toBe(120)
    expect(turnStats.cacheReadTokens).toBe(0)
    expect(turnStats.cacheWriteTokens).toBe(0)
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
    expect(copilotApi.decideApproval).toHaveBeenCalledWith('a1', true, '')
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

  it('刷新后恢复历史：同 id 但 messages 为空时必须真的去拉（回归）', async () => {
    // 模拟刷新：store 从 localStorage 恢复 sessionId，但 messages 还是空的
    useCopilot.setState({ sessionId: 's-restored', messages: [], loadingHistory: false, streaming: false })
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([
      { message_id: 1, role: 'user', content: '你谁啊', created_at: '', metadata: {} },
      { message_id: 2, role: 'assistant', content: '我是助手', created_at: '', metadata: {} },
    ] as AgentHistoryMessage[])

    // 面板挂载时正是这样调：id 与当前 sessionId 相同
    await useCopilot.getState().switchSession('s-restored')

    // 修复前这里被提前 return 短路，fetchHistory 一次都没调
    expect(copilotApi.fetchHistory).toHaveBeenCalledWith('s-restored')
    expect(useCopilot.getState().messages).toHaveLength(2)
    expect(useCopilot.getState().messages[0]?.content).toBe('你谁啊')
  })

  it('已就绪的同会话不重复拉取（切回来不闪、不重复请求）', async () => {
    useCopilot.setState({
      sessionId: 's-ready',
      messages: [{ id: 'm1', role: 'user', content: '在的' }],
      loadingHistory: false,
      streaming: false,
    })
    vi.mocked(copilotApi.fetchHistory).mockClear()
    await useCopilot.getState().switchSession('s-ready')
    expect(copilotApi.fetchHistory).not.toHaveBeenCalled()
  })
})
