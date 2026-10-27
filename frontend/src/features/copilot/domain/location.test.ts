import { describe, expect, it } from 'vitest'

import type { AgentSession } from '../types'
import { describeLocation, groupSessions } from './location'

describe('describeLocation（路由 → 页面描述）', () => {
  it('详情页由页面自己覆盖精确值，其余按前缀兜底', () => {
    expect(describeLocation('/')).toBe('工作台首页')
    expect(describeLocation('/projects')).toBe('办案列表页')
    expect(describeLocation('/projects/386')).toBe('委托详情页')
    expect(describeLocation('/material-prep')).toBe('材料预处理台')
    // 未收录的路由原样带出，模型至少知道自己在哪个页面
    expect(describeLocation('/finance/invoices')).toBe('页面 /finance/invoices')
  })
})

describe('groupSessions（按业务范围分组）', () => {
  const mk = (o: Partial<AgentSession> & Pick<AgentSession, 'session_id' | 'updated_at'>): AgentSession => ({
    title: o.session_id,
    llm_model: '',
    created_at: o.updated_at,
    ...o,
  } as AgentSession)

  it('案件/合同取 scope_name，任务与通用兜底组，组间按最新排序', () => {
    const groups = groupSessions([
      mk({ session_id: 'chat-1', updated_at: '2026-10-23T10:00:00' }),
      mk({ session_id: 'c-1', updated_at: '2026-10-23T12:00:00', origin: 'contract', contract_id: 390, scope_name: '贵州某公司' }),
      mk({ session_id: 'c-2', updated_at: '2026-10-23T11:00:00', origin: 'contract', contract_id: 390, scope_name: '贵州某公司' }),
      mk({ session_id: 'k-1', updated_at: '2026-10-23T09:00:00', origin: 'case', case_id: 217, scope_name: '' }),
      mk({ session_id: 't-1', updated_at: '2026-10-23T08:00:00', origin: 'task' }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['contract:390', 'chat', 'case:217', 'task'])
    const [contractGroup, , caseGroup, taskGroup] = groups
    expect(contractGroup).toMatchObject({ kind: 'contract', label: '贵州某公司' })
    expect(contractGroup?.sessions.map((s) => s.session_id)).toEqual(['c-1', 'c-2'])
    // scope_name 缺失回退「案件 #id」
    expect(caseGroup?.label).toBe('案件 #217')
    expect(taskGroup).toMatchObject({ kind: 'task', label: '后台任务' })
  })
})
