// @vitest-environment jsdom
/**
 * 审批卡按栏归位（jsdom）：多栏并答时，卡上要能看出是哪一栏要动库表。
 *
 * 直接喂 `approval_request` 帧走完「帧 → store → 卡片」整条链（不手搓
 * PendingApproval），锁住三件事：
 * - 帧带 `agent`/`run_id` → 多栏卡显示栏标签；
 * - 帧不带（旧后端）→ 不报错、不显示标签；
 * - 单栏轮次即便帧带 agent 也不记来源（没有「哪一栏」可分，标签只会是噪声）。
 *
 * 另锁「同名工具两栏同时挂起」：两张卡按 approval_id 各自存在、各自决定，
 * 绝不按 tool_name 去重（那会让其中一栏的操作被另一栏的卡顶掉）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  // 登录/接入模型入口（AnswerAgentMenu 的 qoder 行会调）
  startQoderLogin: vi.fn(),
  fetchQoderLoginStatus: vi.fn(),
  registerQoderByok: vi.fn(),
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

import * as copilotApi from '../api'
import { useCopilot } from '../store'
import type { AgentBackendOption, AgentSession } from '../types'
import { ApprovalCard } from './ApprovalCard'

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

function option(kind: string): AgentBackendOption {
  return {
    kind,
    label: kind,
    description: '',
    available: true,
    reason: '',
    capabilities: { streaming: true, approval: true },
  }
}

/** 跑一轮流：`answerAgents` 决定栏数（[] = 单栏），返回后 approvals 已入列 */
async function runTurn(frames: string[], answerAgents: string[]): Promise<void> {
  useCopilot.setState({ backends: [option('pi'), option('dsh')], answerAgents })
  vi.mocked(copilotApi.createSession).mockResolvedValue(session)
  vi.mocked(copilotApi.openMessageStream).mockResolvedValue(sseResponse(frames))
  await useCopilot.getState().send('查一下')
}

function approvalFrame(id: string, extra: Record<string, unknown> = {}): string {
  return `data: ${JSON.stringify({
    type: 'approval_request',
    approval_id: id,
    tool_name: 'mcp__fachuan__delete_case',
    tool_args: {},
    message: '即将删除案件',
    ...extra,
  })}\n\n`
}

const doneFrame = 'data: {"type":"done","session_id":"s-1","agents":["pi","dsh"]}\n\n'

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
})

describe('审批卡：帧 → store → 卡片', () => {
  it('多栏帧带 agent/run_id：卡上显示该栏标签', async () => {
    await runTurn(
      [approvalFrame('a1', { agent: 'dsh', run_id: 's-1:dsh:1' }), doneFrame],
      ['pi', 'dsh'],
    )

    const approval = useCopilot.getState().approvals[0]!
    expect(approval.agent).toBe('dsh')
    expect(approval.runId).toBe('s-1:dsh:1')

    const { container } = render(<ApprovalCard approval={approval} />)
    expect(container.querySelector('[data-testid="approval-agent"]')?.textContent).toBe('DeepSeek Harness')
    container.remove()
  })

  it('多栏帧不带 agent（旧后端）：不报错、不显示标签', async () => {
    await runTurn([approvalFrame('a1'), doneFrame], ['pi', 'dsh'])

    const approval = useCopilot.getState().approvals[0]!
    expect(approval.agent).toBe('')
    expect(useCopilot.getState().lastError).toBeNull()

    const { container } = render(<ApprovalCard approval={approval} />)
    expect(container.querySelector('[data-testid="approval-agent"]')).toBeNull()
    container.remove()
  })

  it('单栏轮次帧带 agent：仍不记来源（没有第二栏可分，标签是无意义噪声）', async () => {
    await runTurn([approvalFrame('a1', { agent: 'pi', run_id: 's-1:pi:1' }), doneFrame], [])

    const approval = useCopilot.getState().approvals[0]!
    expect(approval.agent).toBe('')
    expect(approval.runId).toBe('s-1:pi:1')

    const { container } = render(<ApprovalCard approval={approval} />)
    expect(container.querySelector('[data-testid="approval-agent"]')).toBeNull()
    container.remove()
  })
})

describe('审批卡：同名工具两栏同时挂起', () => {
  it('两张卡共存且能各自决定（按 approval_id，不按 tool_name 去重）', async () => {
    vi.mocked(copilotApi.decideApproval).mockResolvedValue({})
    await runTurn(
      [
        approvalFrame('a-pi', { agent: 'pi', run_id: 's-1:pi:1' }),
        approvalFrame('a-dsh', { agent: 'dsh', run_id: 's-1:dsh:1' }),
        doneFrame,
      ],
      ['pi', 'dsh'],
    )

    const approvals = useCopilot.getState().approvals
    expect(approvals.map((a) => a.approvalId)).toEqual(['a-pi', 'a-dsh'])

    const { container } = render(
      <>
        {approvals.map((a) => (
          <ApprovalCard key={a.approvalId} approval={a} />
        ))}
      </>,
    )
    expect(screen.getAllByTestId('approval-agent').map((el) => el.textContent)).toEqual([
      'Pi',
      'DeepSeek Harness',
    ])

    const approveButtons = screen.getAllByRole('button', { name: '同意' })
    expect(approveButtons).toHaveLength(2)
    fireEvent.click(approveButtons[0]!)
    fireEvent.click(approveButtons[1]!)

    await waitFor(() => expect(copilotApi.decideApproval).toHaveBeenCalledTimes(2))
    expect(copilotApi.decideApproval).toHaveBeenNthCalledWith(1, 'a-pi', true, '')
    expect(copilotApi.decideApproval).toHaveBeenNthCalledWith(2, 'a-dsh', true, '')
    container.remove()
  })

  it('同一 approval_id 重放只留一张（按 id 去重，同名工具的另一栏不受影响）', async () => {
    await runTurn(
      [
        approvalFrame('a-pi', { agent: 'pi' }),
        approvalFrame('a-pi', { agent: 'pi' }), // 重放/重连
        approvalFrame('a-dsh', { agent: 'dsh' }), // 同名工具、不同 id
        doneFrame,
      ],
      ['pi', 'dsh'],
    )

    expect(useCopilot.getState().approvals.map((a) => a.approvalId)).toEqual(['a-pi', 'a-dsh'])
  })
})
