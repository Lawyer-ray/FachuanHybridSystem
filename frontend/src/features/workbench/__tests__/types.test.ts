/**
 * Workbench Types Tests
 * 测试工作台模块的 Agent 选项常量
 */

import { AGENT_OPTIONS } from '../types'
import type { AgentType } from '../types'

const AGENT_TYPE_VALUES: AgentType[] = ['triage', 'case', 'contract', 'research']

describe('AGENT_OPTIONS', () => {
  it('defines 4 agent options', () => {
    expect(AGENT_OPTIONS).toHaveLength(4)
  })

  it('each option has type, name, and description', () => {
    for (const opt of AGENT_OPTIONS) {
      expect(opt.type).toBeTruthy()
      expect(opt.name).toBeTruthy()
      expect(opt.description).toBeTruthy()
    }
  })

  it('covers all AgentType values', () => {
    const types = AGENT_OPTIONS.map((o) => o.type)
    for (const val of AGENT_TYPE_VALUES) {
      expect(types).toContain(val)
    }
  })

  it('has no duplicate types', () => {
    const types = AGENT_OPTIONS.map((o) => o.type)
    expect(new Set(types).size).toBe(types.length)
  })

  it('defines expected agents', () => {
    const byType = Object.fromEntries(AGENT_OPTIONS.map((o) => [o.type, o]))
    expect(byType.triage.name).toBe('分诊助手')
    expect(byType.case.name).toBe('案件管理')
    expect(byType.contract.name).toBe('合同管理')
    expect(byType.research.name).toBe('法律检索')
  })
})
