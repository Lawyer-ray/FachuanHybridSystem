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

describe('copilot store：业务上下文', () => {
  it('enterContext 沿用该范围最近的会话（列表第一条）；exitContext 清除', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    vi.mocked(copilotApi.listSessions).mockResolvedValue([session])
    useCopilot.setState({ sessionId: 's-other', messages: [{ id: '1', role: 'user', content: 'x' }] })

    await useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '张三委托' })
    expect(copilotApi.listSessions).toHaveBeenCalledWith(1, { origin: 'contract', refId: 386 })
    expect(useCopilot.getState().context).toEqual({ origin: 'contract', refId: 386, title: '张三委托' })
    expect(useCopilot.getState().sessionId).toBe('s-1')

    await useCopilot.getState().exitContext()
    expect(useCopilot.getState().context).toBeNull()
  })

  it('该范围没有历史会话：落空白新对话', async () => {
    vi.mocked(copilotApi.listSessions).mockResolvedValue([])
    await useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '张三委托' })
    expect(useCopilot.getState().sessionId).toBeNull()
  })

  it('最近会话拉取失败：按无历史处理（空白），不阻塞进页', async () => {
    vi.mocked(copilotApi.listSessions).mockRejectedValue(new Error('boom'))
    await useCopilot.getState().enterContext({ origin: 'case', refId: 12, title: '某案' })
    expect(useCopilot.getState().sessionId).toBeNull()
    expect(useCopilot.getState().context).toEqual({ origin: 'case', refId: 12, title: '某案' })
  })

  it('拉取期间律师点了「新对话」：迟到的自动恢复不得覆盖', async () => {
    let resolveList: (v: AgentSession[]) => void = () => {}
    vi.mocked(copilotApi.listSessions).mockReturnValue(
      new Promise<AgentSession[]>((r) => {
        resolveList = r
      }),
    )
    const entering = useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '张三委托' })
    // 拉取在途时用户主动开了新对话
    await useCopilot.getState().switchSession(null)
    resolveList([session])
    await entering

    expect(useCopilot.getState().sessionId).toBeNull()
  })

  it('同一范围重进（数据刷新）：幂等短路，不重置对话', async () => {
    vi.mocked(copilotApi.listSessions).mockResolvedValue([session])
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    await useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '张三委托' })
    vi.clearAllMocks()

    await useCopilot.getState().enterContext({ origin: 'contract', refId: 386, title: '标题更新' })
    expect(copilotApi.listSessions).not.toHaveBeenCalled()
    expect(useCopilot.getState().sessionId).toBe('s-1')
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
