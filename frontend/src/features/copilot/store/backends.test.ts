/**
 * 后端能力 → 技能送达三态（`/` 菜单的降级提示数据源）。
 *
 * 三态的判据必须锁在纯函数上：`/` 菜单每次打开都要算一次，而「全支持不提示、
 * 混合只提示不一致、仅工具要给绕法」这三种结果对应的用户动作完全不同。
 * 另锁两条缺省口径：清单里查不到 ≠ tool_only（不告警），老后端没声明字段 = tool_only。
 */

import { describe, expect, it } from 'vitest'

import type { AgentBackendOption, BackendCapabilities } from '../backend-types'
import { SKILL_DELIVERY_HINTS, classifySkillDelivery, skillDeliveryOf } from './backends'

function option(kind: string, capabilities: BackendCapabilities = {}): AgentBackendOption {
  return { kind, label: kind, description: '', available: true, reason: '', capabilities }
}

const pi = option('pi', { streaming: true, skill_delivery: 'prompt' })
const qoder = option('qoder', { streaming: true, skill_delivery: 'prompt' })
const codex = option('codex', { streaming: true, skill_delivery: 'tool_only' })

describe('skillDeliveryOf：缺省口径', () => {
  it('清单里查不到的后端返回 null（判不了，不能按最差档告警）', () => {
    expect(skillDeliveryOf([pi], 'not-listed')).toBeNull()
    expect(skillDeliveryOf([], 'pi')).toBeNull()
  })

  it('查到了但没声明 skill_delivery 的老后端按 tool_only', () => {
    expect(skillDeliveryOf([option('legacy', { streaming: true })], 'legacy')).toBe('tool_only')
  })
})

describe('classifySkillDelivery：三态聚合', () => {
  it('全支持：所有在跑后端都注索引 → full，且没有提示文案', () => {
    expect(classifySkillDelivery([pi, qoder], ['pi', 'qoder'])).toBe('full')
    expect(SKILL_DELIVERY_HINTS).not.toHaveProperty('full')
  })

  it('混合降级：部分后端只能按需取 → mixed，提示「自主命中可能不一致」', () => {
    const tier = classifySkillDelivery([pi, codex], ['pi', 'codex'])
    expect(tier).toBe('mixed')
    expect(SKILL_DELIVERY_HINTS.mixed).toBe('部分后端只能靠工具按需取技能，自主命中可能不一致')
  })

  it('仅工具：全部 tool_only → tool_only，提示点名 /skill:名字', () => {
    const tier = classifySkillDelivery([codex, option('cline', { skill_delivery: 'tool_only' })], ['codex', 'cline'])
    expect(tier).toBe('tool_only')
    expect(SKILL_DELIVERY_HINTS.tool_only).toContain('/skill:名字')
    expect(SKILL_DELIVERY_HINTS.tool_only).toContain('list_my_skills')
  })

  it('没有在跑的后端 / 清单里查不到其中一个 → null（宁可不报，也不制造假降级）', () => {
    expect(classifySkillDelivery([pi, codex], [])).toBeNull()
    expect(classifySkillDelivery([pi], ['pi', 'not-listed'])).toBeNull()
  })
})
