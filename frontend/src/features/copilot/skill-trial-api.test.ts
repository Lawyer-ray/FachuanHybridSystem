/**
 * 试跑回执归一化：**服务端字段缺省时的唯一降级点**。
 *
 * 这个文件存在的理由是两条只有真看代码才会想到的约定：
 *
 * 1. ★ 字段（`mode` / `tool_errors` / `trial_id`）在后端未升级时会**缺失**。缺失要保持
 *    缺失（`undefined`），不能补默认值——补一个 `'inline'` 会让界面显示一个从未发生过的
 *    模式，比不显示更糟；
 * 2. `model` 报不出来时归一成 `null` 而不是 `''`：界面据此**整项不渲染**，渲染成 "null"
 *    会让人以为模型坏了。
 *
 * 另外 `mode` 是白名单过滤的：后端将来加一个新模式值时，界面不该显示一个读不懂的枚举。
 */
import { describe, expect, it } from 'vitest'

import { normalizeAgentSkillTrial, normalizeAgentSkillTrialQuota } from './skill-trial-api'

describe('normalizeAgentSkillTrial', () => {
  it('完整回执原样透传', () => {
    const result = normalizeAgentSkillTrial({
      ok: true,
      text: '先输出结论',
      backend: 'pi',
      model: 'kimi-2.6',
      duration_ms: 2722,
      skill_key: 'skill:abc',
      skill_name: 'contract-review',
      skill_scope: 'law_firm',
      skill_version: 3,
      injected: '<skill>…</skill>',
      tool_calls: ['mcp__fachuan__get_agent_skill'],
      error: '',
      mode: 'index',
      tool_errors: [{ tool: 'get_agent_skill', message: '未发布' }],
      trial_id: 't-1',
    })
    expect(result.mode).toBe('index')
    expect(result.model).toBe('kimi-2.6')
    expect(result.tool_errors).toHaveLength(1)
    expect(result.trial_id).toBe('t-1')
  })

  it('★ 字段缺失时保持缺失，不补默认值', () => {
    const result = normalizeAgentSkillTrial({ ok: false, text: '' })
    expect(result.mode).toBeUndefined()
    expect(result.tool_errors).toBeUndefined()
    expect(result.trial_id).toBeUndefined()
  })

  it('model 缺失归一成 null（界面据此整项不渲染，而不是显示空串）', () => {
    expect(normalizeAgentSkillTrial({ ok: true, text: 'x' }).model).toBeNull()
  })

  it('未知 mode 不显示（白名单过滤，避免界面出现读不懂的枚举）', () => {
    const result = normalizeAgentSkillTrial({ ok: true, text: 'x', mode: 'telepathy' as never })
    expect(result.mode).toBeUndefined()
  })

  it('tool_errors 里的脏项被剔掉，不整段炸掉', () => {
    const result = normalizeAgentSkillTrial({
      ok: true,
      text: 'x',
      tool_errors: [{ tool: 'get_agent_skill' }, { message: '没有 tool 字段' }, null, 'garbage'] as never,
    })
    expect(result.tool_errors).toEqual([{ tool: 'get_agent_skill', message: '' }])
  })
})

describe('normalizeAgentSkillTrialQuota', () => {
  it('有 limit 时推得出 remaining', () => {
    expect(normalizeAgentSkillTrialQuota({ limit: 30, used: 4 })).toEqual({
      limit: 30,
      used: 4,
      remaining: 26,
      reset_at: undefined,
    })
  })

  it('服务端直接给了 remaining 就用它', () => {
    expect(normalizeAgentSkillTrialQuota({ limit: 30, used: 30, remaining: 0 }).remaining).toBe(0)
  })

  it('「不知道额度」保持 undefined，不能推成 0（否则按钮被误禁用）', () => {
    expect(normalizeAgentSkillTrialQuota({}).remaining).toBeUndefined()
  })

  it('remaining 不会被推成负数', () => {
    expect(normalizeAgentSkillTrialQuota({ limit: 3, used: 9 }).remaining).toBe(0)
  })
})
