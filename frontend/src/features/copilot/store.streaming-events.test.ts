import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { activityText } from './domain'
import { useCopilot } from './store'
import type { AgentBackendOption, AgentSession } from './types'

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
  agent_kind: 'pi',
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

  it('error 事件：code / scope / detail 不得在流式层被丢掉', async () => {
    // 回归夜（2026-11-24）：`streaming.ts` 曾经只转发 `event.message`，把后端已经
    // 给了的 code/scope/detail 全扔了 → 会话不存在被报成「未知错误」，诊断里连
    // which session 都看不到。这里从帧到 store 走一遍，锁住整条链路。
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"error","message":"会话不存在","code":"session_not_found","scope":"request","agent":"pi","detail":{"session_id":"s-1"}}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')
    const raw = useCopilot.getState().lastError!
    expect(raw).toContain('会话不存在')
    // 信封里必须带着三件套，否则最后一个环节的 classifyError 只能按文案猜
    expect(raw).toContain('session_not_found')
    expect(raw).toContain('s-1')
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

// ============ 单栏可观测性 / 缺 done 的收尾 / EOF 尾帧（流式健壮性） ============

/** 可逐步喂帧的响应（观察**流当中**的状态：同步消费完就什么都看不到了） */
function controlledStream() {
  const handles = { push: (_frame: string) => {}, close: () => {} }
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      handles.push = (frame: string) => controller.enqueue(encoder.encode(frame))
      handles.close = () => controller.close()
    },
  })
  return { resp: new Response(body, { status: 200 }), ...handles }
}

function option(kind: string): AgentBackendOption {
  return {
    kind,
    label: kind,
    description: '',
    available: true,
    reason: '',
    capabilities: {
      streaming: true,
      tool_calls: true,
      approval: true,
      compaction: true,
      steer: true,
      concurrent_in_session: false,
    },
  }
}

const threeBackends = [option('pi'), option('dsh'), option('oai')]

describe('单栏：工具期间的「正在查 XX…」靠 pendingTool（不靠多栏的 tools）', () => {
  it('tool_call 出现 → 说「正在查律师名单…」；tool_result 回来 → 转「正在整理资料…」', async () => {
    // 真实事故：dsh / openai-agents 先调工具、调完才吐正文，中间十几秒界面一片空白
    // （`activityText` 只看 `message.tools`，而单栏永远没有 `tools`）
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    const stream = controlledStream()
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(stream.resp)
    const assistant = () => useCopilot.getState().messages.find((m) => m.role === 'assistant')!

    const sending = useCopilot.getState().send('查下律师')

    stream.push('data: {"type":"tool_call","tool_call_id":"c1","name":"mcp__fachuan__list_lawyers","agent":"pi"}\n\n')
    await vi.waitFor(() => expect(assistant().pendingTool?.toolCallId).toBe('c1'))
    expect(activityText(assistant())).toBe('正在查律师名单…')
    // 单栏的 `tools` 必须保持空：那是多栏的渲染槽，填了工具行会渲染两份
    expect(assistant().tools).toBeUndefined()
    // 转录流里的工具行照旧平铺（单栏那条路径的时间顺序本来就对）
    expect(useCopilot.getState().messages.some((m) => m.role === 'tool' && m.toolCallId === 'c1')).toBe(true)

    stream.push('data: {"type":"tool_result","tool_call_id":"c1","name":"mcp__fachuan__list_lawyers","result":"[]","agent":"pi"}\n\n')
    await vi.waitFor(() => expect(activityText(assistant())).toBe('正在整理资料…'))

    stream.push('data: {"type":"delta","content":"共 3 位律师","agent":"pi"}\n\n')
    stream.push('data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n')
    stream.close()
    await sending

    expect(assistant().content).toBe('共 3 位律师')
    // 收尾后不再有活动行（正文与光标接管）
    expect(activityText(assistant())).toBeNull()
  })

  it('另一栏的工具结果不会清掉本栏的「正在查」', async () => {
    // 多答时两栏的工具交错到达：按 tool_call_id 匹配才不会把 dsh 的结果记到 pi 头上
    useCopilot.setState({ backends: threeBackends, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    const stream = controlledStream()
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(stream.resp)
    const lane = (kind: string) =>
      useCopilot.getState().messages.find((m) => m.role === 'assistant' && m.agentKind === kind)!

    const sending = useCopilot.getState().send('x')
    stream.push('data: {"type":"tool_call","tool_call_id":"p1","name":"get_client","agent":"pi"}\n\n')
    stream.push('data: {"type":"tool_call","tool_call_id":"d1","name":"list_cases","agent":"dsh"}\n\n')
    await vi.waitFor(() => expect(lane('dsh').pendingTool?.toolCallId).toBe('d1'))

    stream.push('data: {"type":"tool_result","tool_call_id":"d1","name":"list_cases","result":"[]","agent":"dsh"}\n\n')
    await vi.waitFor(() => expect(activityText(lane('dsh'))).toBe('正在整理资料…'))
    // pi 那栏仍在等自己的工具
    expect(activityText(lane('pi'))).toBe('正在查客户信息…')

    stream.push('data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n')
    stream.push('data: {"type":"done","session_id":"s-1","agent":"dsh"}\n\n')
    stream.close()
    await sending
  })
})

describe('缺 done 的收尾：不再静默留空栏', () => {
  it('三栏只到一栏 done：缺的两栏标「已中断」，跑完那栏不标、也不标失败', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: ['pi', 'dsh', 'oai'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"pi 的答","agent":"pi"}\n\n',
        'data: {"type":"delta","content":"dsh 的答","agent":"dsh"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')

    const lane = (kind: string) =>
      useCopilot.getState().messages.find((m) => m.role === 'assistant' && m.agentKind === kind)!
    expect(lane('pi').truncated).toBeUndefined()
    expect(lane('dsh').truncated).toBe(true)
    expect(lane('oai').truncated).toBe(true)
    // 「没等到」不是「跑失败」：标成「本轮未做」会让律师以为后端拒绝了这一栏
    expect(lane('dsh').failed).toBeUndefined()
    expect(useCopilot.getState().lastError).toContain('未等到')
    expect(useCopilot.getState().lastError).toContain('dsh / oai')
  })

  it('先降级后断流：被丢下的栏标「本轮未做」，主栏仍标「已中断」（两个独立事实）', async () => {
    // 原先 `lastError !== null` 会拦住标 truncated：降级已经写了 lastError，
    // 于是断流时主栏既不标中断也没有提示——律师看到一句「对比执行位已满」，
    // 却不知道自己的主答案还断在半路
    useCopilot.setState({ backends: threeBackends, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"activity","status":"degraded","agent":"pi","reason":"对比执行位已满"}\n\n',
        'data: {"type":"delta","content":"只有一半","agent":"pi"}\n\n',
        // 没有 done：连接在收尾前被掐断
      ]),
    )

    await useCopilot.getState().send('x')

    const lane = (kind: string) =>
      useCopilot.getState().messages.find((m) => m.role === 'assistant' && m.agentKind === kind)!
    expect(lane('dsh').failed).toBe(true)
    // 已标「本轮未做」的栏不再叠「已中断」（一栏两个徽标读不出到底发生了什么）
    expect(lane('dsh').truncated).toBeUndefined()
    expect(lane('pi').truncated).toBe(true)
    // 更具体的错误优先，不被「未等到…」的提示覆盖
    expect(useCopilot.getState().lastError).toBe('对比执行位已满')
  })

  it('单栏断流（没有 done）：标截断并提示连接提前结束', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"delta","content":"半截","agent":"pi"}\n\n']),
    )

    await useCopilot.getState().send('x')

    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.truncated).toBe(true)
    expect(assistant.streaming).toBe(false)
    expect(useCopilot.getState().lastError).toBe('与本轮的连接提前结束，回答可能不完整')
  })
})

describe('EOF 尾帧：最后一帧即使没有空行结尾也要交付', () => {
  it('尾帧是 done：不标截断、不报错（早先被丢掉 → 正常轮次被当成断流）', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"delta","content":"答","agent":"pi"}\n\n', 'data: {"type":"done","session_id":"s-1","agent":"pi"}']),
    )

    await useCopilot.getState().send('x')

    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.truncated).toBeUndefined()
    expect(useCopilot.getState().lastError).toBeNull()
  })

  it('尾帧是正文：最后一截字也在（不能只认 done）', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"delta","content":"前半句，","agent":"pi"}\n\n', 'data: {"type":"delta","content":"后半句。","agent":"pi"}']),
    )

    await useCopilot.getState().send('x')

    expect(useCopilot.getState().messages.find((m) => m.role === 'assistant')?.content).toBe('前半句，后半句。')
  })

  it('尾帧是 usage：本轮最准的成本数据不丢', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"答","agent":"pi"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
        'data: {"type":"usage","output_tokens":42,"agent":"pi"}',
      ]),
    )

    await useCopilot.getState().send('x')

    expect(useCopilot.getState().turnStats.exactTokens).toBe(42)
  })

  it('压缩中途断流：底栏的「正在压缩上下文…」不会永远转下去', async () => {
    // `compacting` 只能靠 compaction end 事件退场；断流时那个事件永远不来
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"compaction","phase":"start"}\n\n', 'data: {"type":"delta","content":"答","agent":"pi"}\n\n']),
    )

    await useCopilot.getState().send('x')

    expect(useCopilot.getState().compacting).toBe(false)
  })
})

// ============ 逐句溯源：citations 事件（增量，一轮可多次） ============

describe('citations 事件：单栏落到气泡、多答各归各栏', () => {
  it('单栏：citations 追加到该气泡，角标点得开', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"结论见[K1]与[K2]。","agent":"pi"}\n\n',
        'data: {"type":"citations","agent":"pi","run_id":"s-1:pi:1","citations":[{"cite_no":1,"kind":"case","ref_id":217,"name":"某公司诉某银行案","page":4},{"cite_no":2,"kind":"file","name":"委托合同.docx","chunk_id":88}]}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')

    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    // 落库前就能点开：引用挂在实时气泡上（收尾后由 metadata.citations 重建同一份）
    expect(assistant.citations).toEqual([
      { citeNo: 1, kind: 'case', refId: 217, name: '某公司诉某银行案', page: 4 },
      { citeNo: 2, kind: 'file', name: '委托合同.docx', chunkId: 88 },
    ])
  })

  it('多答：两栏各收自己那份，另一栏不受影响（不能写死主栏）', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"citations","agent":"pi","citations":[{"cite_no":1,"kind":"statute","name":"民法典第 577 条"}]}\n\n',
        'data: {"type":"citations","agent":"dsh","citations":[{"cite_no":1,"kind":"contract","name":"委托合同.docx"}]}\n\n',
        'data: {"type":"delta","content":"pi 的答[K1]","agent":"pi"}\n\n',
        'data: {"type":"delta","content":"dsh 的答[K1]","agent":"dsh"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"dsh"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')

    const lane = (kind: string) =>
      useCopilot.getState().messages.find((m) => m.role === 'assistant' && m.agentKind === kind)!
    // 两栏 cite_no 都是 1，但指向不同材料：串栏就会出现「点开的是别人的证据」
    expect(lane('pi').citations).toEqual([{ citeNo: 1, kind: 'statute', name: '民法典第 577 条' }])
    expect(lane('dsh').citations).toEqual([{ citeNo: 1, kind: 'contract', name: '委托合同.docx' }])
  })

  it('增量：同一 cite_no 后到覆盖先到，新编号追加、顺序不变', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"citations","agent":"pi","citations":[{"cite_no":1,"name":"先到的名字","page":1}]}\n\n',
        'data: {"type":"citations","agent":"pi","citations":[{"cite_no":1,"name":"后到的名字","page":9,"text":"原文片段"},{"cite_no":2,"name":"另一条"}]}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')

    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    expect(assistant.citations).toEqual([
      { citeNo: 1, kind: 'file', name: '后到的名字', page: 9, text: '原文片段' },
      { citeNo: 2, kind: 'file', name: '另一条' },
    ])
  })

  it('空载荷 / 全畸形条目不造空表（否则正文角标会被统统降级）', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"citations","agent":"pi","citations":[]}\n\n',
        'data: {"type":"citations","agent":"pi","citations":[{"name":"缺编号.pdf"}]}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')
    expect(useCopilot.getState().messages.find((m) => m.role === 'assistant')?.citations).toBeUndefined()
  })

  it('收尾一致性：正文有合法 [Kn] 但没收到引用表 → 保持 undefined，不补假引用', async () => {
    useCopilot.setState({ backends: threeBackends, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"结论见[K1]。","agent":"pi"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')
    const assistant = useCopilot.getState().messages.find((m) => m.role === 'assistant')!
    // 渲染层已有「引用缺失就降级为纯文本」：在这里按 [K1] 造一条来源只会编出假出处
    expect(assistant.content).toContain('[K1]')
    expect(assistant.citations).toBeUndefined()
  })
})
