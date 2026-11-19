/**
 * store：多答的分流（round-trip 行为，不 mock 分流逻辑本身）。
 *
 * 验收的是「交错到达的多条事件流各归各家」：后端把各 agent 的事件按到达顺序
 * 混在一条 SSE 里推过来，store 必须按事件里的 `agent` 把它们写进不同的 assistant
 * 气泡。分流一旦错位，两栏会显示同一份内容、另一栏永远空白——而界面看起来完全
 * 正常（没有任何报错）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { canAddAnswerAgent, resolveAnswerAgents, resolveAnswerSpecs } from './store/turn'
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
  fetchBackends: vi.fn(),
  fetchSessionStats: vi.fn(),
  compactSession: vi.fn(),
}))

const encoder = new TextEncoder()

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

function option(kind: string, available = true, streaming = true): AgentBackendOption {
  return {
    kind,
    label: kind,
    description: '',
    available,
    reason: '',
    capabilities: {
      streaming,
      tool_calls: true,
      approval: true,
      compaction: true,
      steer: true,
      concurrent_in_session: false,
    },
  }
}

const three = [option('pi'), option('dsh'), option('oai')]

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

describe('resolveAnswerAgents / canAddAnswerAgent（开流前的栏数决策）', () => {
  it('用户选的就本轮要跑的（顺序即栏的左右顺序）', () => {
    expect(resolveAnswerAgents({ backends: three, answerAgents: ['dsh', 'pi'] })).toEqual(['dsh', 'pi'])
  })

  it('没选时返回空数组（不指定 = 后端单跑会话默认后端）', () => {
    expect(resolveAnswerAgents({ backends: three, answerAgents: [] })).toEqual([])
  })

  it('不可用（缺 SDK 置灰）的后端被剔除，不造一个永远空着的栏', () => {
    const backends = [option('pi'), option('dsh', false), option('oai')]
    expect(resolveAnswerAgents({ backends, answerAgents: ['pi', 'dsh', 'oai'] })).toEqual(['pi', 'oai'])
  })

  it('声明不支持流式的后端被剔除（多栏渲染靠流式，非流式后端给不出交错事件）', () => {
    const backends = [option('pi'), option('dsh', true, false)]
    expect(resolveAnswerAgents({ backends, answerAgents: ['pi', 'dsh'] })).toEqual(['pi'])
  })

  it('清单没拉到时信任用户的选择（背压不阻塞多答）', () => {
    expect(resolveAnswerAgents({ backends: [], answerAgents: ['pi', 'dsh'] })).toEqual(['pi', 'dsh'])
  })

  it('超过 MAX_ANSWERS 的部分被截掉（后端会 400，前端先截）', () => {
    const backends = ['a', 'b', 'c', 'd', 'e'].map((k) => option(k))
    expect(resolveAnswerAgents({ backends, answerAgents: ['a', 'b', 'c', 'd', 'e'] })).toEqual(['a', 'b', 'c', 'd'])
  })

  it('canAddAnswerAgent：满 4 个后不能再加', () => {
    expect(canAddAnswerAgent([])).toBe(true)
    expect(canAddAnswerAgent(['a', 'b', 'c'])).toBe(true)
    expect(canAddAnswerAgent(['a', 'b', 'c', 'd'])).toBe(false)
  })
})

describe('resolveAnswerSpecs（每栏带模型）', () => {
  it('没指定模型时只发 kind（缺省字段 = 平台默认，与发纯字符串等价）', () => {
    expect(resolveAnswerSpecs({ backends: three, answerAgents: ['pi', 'dsh'], answerModels: {} })).toEqual([
      { kind: 'pi' },
      { kind: 'dsh' },
    ])
  })

  it('指定了模型的栏带上 model，其余栏仍只有 kind', () => {
    expect(
      resolveAnswerSpecs({ backends: three, answerAgents: ['pi', 'dsh'], answerModels: { dsh: 'glm53' } }),
    ).toEqual([{ kind: 'pi' }, { kind: 'dsh', model: 'glm53' }])
  })

  it('与栏清单同源：不可用的后端剔掉后，模型不会错位挂到别人身上', () => {
    const backends = [option('pi'), option('dsh', false), option('oai')]
    expect(
      resolveAnswerSpecs({
        backends,
        answerAgents: ['pi', 'dsh', 'oai'],
        answerModels: { dsh: 'glm53', oai: 'kimi-2.6' },
      }),
    ).toEqual([{ kind: 'pi' }, { kind: 'oai', model: 'kimi-2.6' }])
  })

  it('没勾选的后端上的模型设置不下发（只作用于本轮真的会跑的栏）', () => {
    expect(resolveAnswerSpecs({ backends: three, answerAgents: ['pi'], answerModels: { dsh: 'glm53' } })).toEqual([
      { kind: 'pi' },
    ])
  })
})

describe('answerModels（每栏指指定的模型）', () => {
  it('setAnswerModel 记下指定，空串即删键（不留两种「用默认」的写法）', () => {
    const { setAnswerModel } = useCopilot.getState()
    setAnswerModel('pi', 'kimi-2.6')
    expect(useCopilot.getState().answerModels).toEqual({ pi: 'kimi-2.6' })
    setAnswerModel('pi', '')
    expect(useCopilot.getState().answerModels).toEqual({})
  })

  it('同一个模型重复选不写状态（不造无意义的新对象）', () => {
    const { setAnswerModel } = useCopilot.getState()
    setAnswerModel('pi', 'kimi-2.6')
    const before = useCopilot.getState().answerModels
    setAnswerModel('pi', 'kimi-2.6')
    expect(useCopilot.getState().answerModels).toBe(before)
  })

  it('登出清空模型选择（清单本身保留）', () => {
    useCopilot.setState({ backends: three, answerModels: { pi: 'kimi-2.6' } })
    useCopilot.getState().reset()
    expect(useCopilot.getState().answerModels).toEqual({})
    expect(useCopilot.getState().backends).toHaveLength(3)
  })
})

describe('answerAgents 的选择（toggleAnswerAgent）', () => {
  it('切换即增删，顺序保持选择顺序', () => {
    const { toggleAnswerAgent } = useCopilot.getState()
    toggleAnswerAgent('dsh')
    toggleAnswerAgent('pi')
    expect(useCopilot.getState().answerAgents).toEqual(['dsh', 'pi'])
    toggleAnswerAgent('dsh')
    expect(useCopilot.getState().answerAgents).toEqual(['pi'])
  })

  it('满 4 个后忽略新增（键盘/程序路径也不能绕过上限）', () => {
    useCopilot.setState({ answerAgents: ['a', 'b', 'c', 'd'] })
    useCopilot.getState().toggleAnswerAgent('e')
    expect(useCopilot.getState().answerAgents).toEqual(['a', 'b', 'c', 'd'])
  })

  it('登出清空选择', () => {
    useCopilot.setState({ answerAgents: ['pi', 'dsh'] })
    useCopilot.getState().reset()
    expect(useCopilot.getState().answerAgents).toEqual([])
  })
})

describe('send 的多答分流', () => {
  it('两条交错的事件流各归各家', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"meta","session_id":"s-1","agent":"pi","agents":["pi","dsh"]}\n\n',
        'data: {"type":"delta","content":"主","agent":"pi","run_id":"s-1:pi:1"}\n\n',
        'data: {"type":"delta","content":"次","agent":"dsh","run_id":"s-1:dsh:1"}\n\n',
        'data: {"type":"delta","content":"答一","agent":"pi","run_id":"s-1:pi:1"}\n\n',
        'data: {"type":"delta","content":"答二","agent":"dsh","run_id":"s-1:dsh:1"}\n\n',
        'data: {"type":"done","session_id":"s-1","agents":["pi","dsh"]}\n\n',
      ]),
    )

    await useCopilot.getState().send('合同有效吗')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(2)
    expect(answers.find((m) => m.agentKind === 'pi')!.content).toBe('主答一')
    expect(answers.find((m) => m.agentKind === 'dsh')!.content).toBe('次答二')
    // 两栏都收尾，不留下「生成中」的光标
    expect(answers.every((m) => m.streaming === false)).toBe(true)
  })

  it('三栏：各栏只写自己的正文', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh', 'oai'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"甲","agent":"pi"}\n\n',
        'data: {"type":"delta","content":"乙","agent":"dsh"}\n\n',
        'data: {"type":"delta","content":"丙","agent":"oai"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('三栏问题')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers.map((m) => m.agentKind)).toEqual(['pi', 'dsh', 'oai'])
    expect(answers.map((m) => m.content)).toEqual(['甲', '乙', '丙'])
  })

  it('回归：各栏各自发 done 且交错到达时，先完成的那栏不能收掉其他栏', async () => {
    // 2026-11-19 真实事故：后端在**每栏**跑完时各发一次 done（带 agent）。
    // 旧实现 onDone 直接调 finishAssistant()（收掉全部 streaming 气泡），
    // 于是 pi 先完成后 dsh 的 delta 无处可写——界面上两栏都是「(无内容)」，
    // 还冒出一句「流处理异常」。这里用「done 早于另一栏的 delta」还原来锁住它。
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"meta","session_id":"s-1","agent":"pi","agents":["pi","dsh"]}\n\n',
        'data: {"type":"delta","content":"主答","agent":"pi","run_id":"s-1:pi:1"}\n\n',
        // pi 先跑完 —— 此刻 dsh 一个字都还没来
        'data: {"type":"done","session_id":"s-1","agent":"pi","agents":["pi","dsh"]}\n\n',
        // dsh 随后才开始吐字（真实的交错形状）
        'data: {"type":"delta","content":"次答","agent":"dsh","run_id":"s-1:dsh:1"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"dsh","agents":["pi","dsh"]}\n\n',
      ]),
    )

    await useCopilot.getState().send('你知道我是谁吗')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(2)
    // 关键断言：dsh 落后于 pi 的 done 到达，内容仍必须写进去
    expect(answers.find((m) => m.agentKind === 'dsh')!.content).toBe('次答')
    expect(answers.find((m) => m.agentKind === 'pi')!.content).toBe('主答')
    expect(answers.every((m) => m.streaming === false)).toBe(true)
  })

  it('回归：多栏时完成时间不记在先完成那栏的 done 上', async () => {
    // 若 onDone 无条件写 doneAt，多答的「本轮完成时间」会变成先完成那栏的时刻，
    // 轮次统计偏早（律师看到的耗时比实际短）。
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"A","agent":"pi","run_id":"s-1:pi:1"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
        'data: {"type":"delta","content":"B","agent":"dsh","run_id":"s-1:dsh:1"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"dsh"}\n\n',
      ]),
    )

    await useCopilot.getState().send('q')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(2)
    expect(answers.find((m) => m.agentKind === 'dsh')!.content).toBe('B')
    // 两栏都收尾了，doneAt 才应被写
    expect(useCopilot.getState().turnStats.doneAt).not.toBeNull()
  })

  it('选中的 agent 清单原样下发（顺序即栏序，未指定模型时只发 kind）', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['dsh', 'pi'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), [
      { kind: 'dsh' },
      { kind: 'pi' },
    ])
  })

  it('各栏点名的模型随请求下发（后端据此跑不同模型）', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'], answerModels: { dsh: 'glm53' } })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), [
      { kind: 'pi' },
      { kind: 'dsh', model: 'glm53' },
    ])
  })

  it('各栏气泡带上本轮指定的模型（栏头「agent · 模型」的数据源）', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'], answerModels: { pi: 'kimi-2.6' } })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers.find((m) => m.agentKind === 'pi')!.model).toBe('kimi-2.6')
    // 没指定模型的栏不写：栏头只显示 agent 名
    expect(answers.find((m) => m.agentKind === 'dsh')!.model).toBeUndefined()
  })

  it('单栏不写模型（单栏不显示「· 模型」，避免噪音）', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi'], answerModels: { pi: 'kimi-2.6' } })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(1)
    expect(answers[0]!.model).toBeUndefined()
  })

  it('没选时不发 agents（保持单后端行为与请求体不变）', async () => {
    useCopilot.setState({ backends: three, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), [])
    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    // 单栏：行为与引入多答前一致（一条不带 agentKind 的回答）
    expect(answers).toHaveLength(1)
    expect(answers[0]!.agentKind).toBeUndefined()
  })

  it('只选了一个可用后端时仍走单栏，但请求体带上它', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), [{ kind: 'dsh' }])
    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(1)
    // 单栏不加来源标签：与引入多答前的渲染完全一致
    expect(answers[0]!.agentKind).toBeUndefined()
  })

  it('只有一栏失败时错误行标明是谁，那一栏标「本轮未做」，其他栏照常显示', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"delta","content":"主答","agent":"pi"}\n\n',
        'data: {"type":"error","message":"该 agent 本轮运行失败","agent":"dsh"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
    )

    await useCopilot.getState().send('x')

    // 错误行必须带来源：否则屏幕上半截明明有答案，却像整轮都失败了
    expect(useCopilot.getState().lastError).toBe('dsh：该 agent 本轮运行失败')
    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    const pi = answers.find((m) => m.agentKind === 'pi')
    const dsh = answers.find((m) => m.agentKind === 'dsh')
    expect(pi?.content).toBe('主答')
    expect(pi?.failed).toBeUndefined()
    // 失败那栏要被标记，UI 才会写「本轮未做」而不是留一个空白栏头
    expect(dsh?.failed).toBe(true)
    expect(dsh?.streaming).toBe(false)
  })

  it('回归：单栏轮次的事件带 agent 时正文照常写入（不写进不存在的气泡）', async () => {
    // 单栏气泡没有登记在任何 kind 名下（只有多栏才建 assistantByAgent）。
    // 早先按「事件 kind 直接查路由表」的实现会让这类单栏轮次整轮空白——
    // 而这正是**不开多答的默认路径**，一旦坏掉就是全员白屏。
    useCopilot.setState({ backends: three, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"meta","session_id":"s-1","agent":"pi"}\n\n',
        'data: {"type":"delta","content":"单栏正文","agent":"pi","run_id":"s-1:pi:1"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('单栏问题')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    expect(answers).toHaveLength(1)
    expect(answers[0]!.content).toBe('单栏正文')
    expect(answers[0]!.streaming).toBe(false)
  })

  it('回归：后端降级（agents 收窄为单栏）时仍写成一条，不造空白栏', async () => {
    // aux 席位满时后端只跑主后端，并按收窄后的 agents 逐栏发 done。
    // 前端若仍按「选了几栏」硬造气泡，就会多出一个永远空着的栏。
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"meta","session_id":"s-1","agent":"pi","agents":["pi"]}\n\n',
        'data: {"type":"activity","status":"degraded","agent":"pi","reason":"对比执行位已满"}\n\n',
        'data: {"type":"delta","content":"只有主答","agent":"pi"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi","agents":["pi"]}\n\n',
      ]),
    )

    await useCopilot.getState().send('降级问题')

    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    // 前端在开流前按选择建了两栏（那时还不知道降级）；正文必须落在主栏上
    expect(answers.find((m) => m.content === '只有主答')!.agentKind).toBe('pi')
    // 全部气泡都收尾，不留转圈光标（降级那栏不发 done，只能靠降级事件收）
    expect(answers.every((m) => m.streaming === false)).toBe(true)
    // 被丢下的那栏标「本轮未做」；主栏不标
    expect(answers.find((m) => m.agentKind === 'dsh')!.failed).toBe(true)
    expect(answers.find((m) => m.agentKind === 'pi')!.failed).toBeUndefined()
    // 降级原因要说出来，否则律师以为对比没生效
    expect(useCopilot.getState().lastError).toBe('对比执行位已满')
  })

  it('降级事件不带 reason 时用兜底文案（不显示空白提示）', async () => {
    useCopilot.setState({ backends: three, answerAgents: ['pi', 'dsh'] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse([
        'data: {"type":"activity","status":"degraded","agent":"pi"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"pi"}\n\n',
      ]),
    )

    await useCopilot.getState().send('降级问题')

    expect(useCopilot.getState().lastError).toBe('本轮只跑了主后端')
  })

  it('单栏轮次失败不标来源（文案与引入多答前一致）', async () => {
    useCopilot.setState({ backends: three, answerAgents: [] })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(
      sseResponse(['data: {"type":"error","message":"本轮运行失败","agent":"pi"}\n\n']),
    )

    await useCopilot.getState().send('x')

    expect(useCopilot.getState().lastError).toBe('本轮运行失败')
  })
})
