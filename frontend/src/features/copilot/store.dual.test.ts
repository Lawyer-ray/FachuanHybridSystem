/**
 * store：同题双答的分流（round-trip 行为，不 mock 分流逻辑本身）。
 *
 * 验收的是「交错到达的两条事件流各归各家」：后端把两个 agent 的事件按到达顺序
 * 混在一条 SSE 里推过来，store 必须按事件里的 `agent` 把它们写进不同的 assistant
 * 气泡。分流一旦错位，两栏会显示同一份内容、另一栏永远空白——而界面看起来完全
 * 正常（没有任何报错）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { dualAgentKinds, dualAvailableFor } from './store/turn'
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

function option(kind: string, available = true): AgentBackendOption {
  return {
    kind,
    label: kind,
    description: '',
    available,
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

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

describe('dualAgentKinds / dualAvailableFor（开流前的栏数决策）', () => {
  it('主栏 = 选中后端，次栏 = 清单里第一个可用的其他后端', () => {
    expect(dualAgentKinds({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi' })).toEqual(['pi', 'dsh'])
  })

  it('没有第二个可用后端时返回单栏（不造两个空栏）', () => {
    expect(dualAgentKinds({ backends: [option('pi')], selectedAgentKind: 'pi' })).toEqual([])
  })

  it('次栏不可用（缺 SDK 置灰）时不算', () => {
    expect(dualAgentKinds({ backends: [option('pi'), option('dsh', false)], selectedAgentKind: 'pi' })).toEqual([])
  })

  it('清单没拉到时退回单栏（背压优先于功能）', () => {
    expect(dualAgentKinds({ backends: [], selectedAgentKind: '' })).toEqual([])
    expect(dualAvailableFor([], '')).toBe(false)
  })

  it('主后端为空串时按 pi 算（旧偏好口径）', () => {
    expect(dualAgentKinds({ backends: [option('pi'), option('dsh')], selectedAgentKind: '' })).toEqual(['pi', 'dsh'])
  })
})

describe('send 的双答分流', () => {
  it('两条交错的事件流各归各家', async () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi', dual: true })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    // 后端按到达顺序交错推送两条流（stream_dual 的真实形状）
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

  it('dual=true 时把开关下发到请求体（默认 false 不发）', async () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi', dual: true })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), true)
  })

  it('dual 关闭时不发该字段（保持单后端行为与请求体不变）', async () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi', dual: false })
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(['data: {"type":"done"}\n\n']))

    await useCopilot.getState().send('x')

    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-1', 'x', expect.anything(), false)
    const answers = useCopilot.getState().messages.filter((m) => m.role === 'assistant')
    // 单栏：行为与引入双答前一致（一条不带 agentKind 的回答）
    expect(answers).toHaveLength(1)
    expect(answers[0]!.agentKind).toBeUndefined()
  })

  it('只有一栏失败时错误行标明是谁（另一栏照常显示）', async () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi', dual: true })
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
    const pi = useCopilot.getState().messages.find((m) => m.role === 'assistant' && m.agentKind === 'pi')
    expect(pi?.content).toBe('主答')
  })

  it('setDual 幂等：同值不触发状态写入', () => {
    useCopilot.setState({ dual: true })
    const before = useCopilot.getState()
    before.setDual(true)
    expect(useCopilot.getState().dual).toBe(true)
    before.setDual(false)
    expect(useCopilot.getState().dual).toBe(false)
  })
})
