import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'

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
beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
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
