import { describe, expect, it } from 'vitest'

import {
  APPROVAL_CRITICAL_WINDOW_S,
  APPROVAL_OFFLINE_WINDOW_S,
  APPROVAL_WINDOW_S,
  approvalWindowSec,
  isExpiredOfflineItem,
  pendingItemToApproval,
  previewToolArgs,
  taskBadge,
} from './approval'

describe('审批倒计时口径', () => {
  it('窗口常量与后端 approval.py 同步：在线 300 / 紧急 900 / 离线 7200', () => {
    expect(APPROVAL_WINDOW_S).toBe(300)
    expect(APPROVAL_CRITICAL_WINDOW_S).toBe(900)
    expect(APPROVAL_OFFLINE_WINDOW_S).toBe(7200)
  })

  it('approvalWindowSec：离线优先，其次按风险等级取紧急窗口', () => {
    expect(approvalWindowSec(undefined)).toBe(APPROVAL_WINDOW_S)
    expect(approvalWindowSec('high')).toBe(APPROVAL_WINDOW_S)
    expect(approvalWindowSec('critical')).toBe(APPROVAL_CRITICAL_WINDOW_S)
    // 离线挂起不论等级一律两小时（后台任务无人可问）
    expect(approvalWindowSec('critical', true)).toBe(APPROVAL_OFFLINE_WINDOW_S)
    expect(approvalWindowSec('low', true)).toBe(APPROVAL_OFFLINE_WINDOW_S)
  })

  it('isExpiredOfflineItem：超出 7200s 才算超期，坏日期按未超期兜底', () => {
    const created = new Date('2026-10-23T10:00:00Z')
    const base = { approval_id: 'x', session_id: 's', tool_name: 't', tool_args: {}, risk_level: 'high', created_at: created.toISOString() }
    expect(isExpiredOfflineItem(base, created.getTime() + 7200 * 1000)).toBe(false)
    expect(isExpiredOfflineItem(base, created.getTime() + 7200 * 1000 + 1)).toBe(true)
    // 坏日期：宁多留一张卡也不误杀
    expect(isExpiredOfflineItem({ ...base, created_at: '不是日期' }, Date.now())).toBe(false)
  })
})

describe('离线待审项 → 审批卡', () => {
  it('字段映射 + offline 标记；created_at 坏值退回当前时间', () => {
    const item = {
      approval_id: 'off-1',
      session_id: 't-9',
      tool_name: 'mcp__fachuan__delete_case',
      tool_args: { case_id: 1 },
      risk_level: 'high',
      created_at: '2026-10-23T10:00:00Z',
    }
    expect(pendingItemToApproval(item)).toEqual({
      approvalId: 'off-1',
      toolName: 'mcp__fachuan__delete_case',
      toolArgs: { case_id: 1 },
      message: '',
      receivedAt: new Date('2026-10-23T10:00:00Z').getTime(),
      riskLevel: 'high',
      offline: true,
    })
    expect(pendingItemToApproval({ ...item, created_at: '坏日期' }).receivedAt).toBeGreaterThan(0)
  })

  it('tool_args 缺失兜底成空对象（审批卡渲染不炸）', () => {
    const r = pendingItemToApproval({
      approval_id: 'a',
      session_id: 's',
      tool_name: 't',
      risk_level: 'low',
      created_at: '2026-10-23T10:00:00Z',
    } as never)
    expect(r.toolArgs).toEqual({})
  })
})

describe('展示归一', () => {
  it('previewToolArgs 空对象为空串、超长截断', () => {
    expect(previewToolArgs({})).toBe('')
    expect(previewToolArgs(undefined)).toBe('')
    expect(previewToolArgs({ a: 1 })).toBe('{"a":1}')
    expect(previewToolArgs({ k: 'x'.repeat(200) }, 50).endsWith('…')).toBe(true)
  })

  it('taskBadge：任务态映射到 label + 语义色档，非任务态为 null', () => {
    expect(taskBadge('queued')).toEqual({ label: '排队中', tone: 'yellow' })
    expect(taskBadge('running')).toEqual({ label: '运行中', tone: 'blue' })
    expect(taskBadge('succeeded')).toEqual({ label: '已完成', tone: 'green' })
    expect(taskBadge('failed')).toEqual({ label: '失败', tone: 'red' })
    expect(taskBadge('cancelled')).toEqual({ label: '已取消', tone: 'neutral' })
    expect(taskBadge(undefined)).toBeNull()
    expect(taskBadge('')).toBeNull()
  })
})
