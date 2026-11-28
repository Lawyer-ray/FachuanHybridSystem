import { describe, expect, it } from 'vitest'

import type { AgentSkill } from '../types'
import { buildSlashMenuItems, filterSlashMenuItems, slashMenuQuery } from './slash'

/** 技能清单项（P0 契约 §1.6 的形状；测试只关心 name/source/enabled） */
function skill(overrides: Partial<AgentSkill> & Pick<AgentSkill, 'name' | 'description'>): AgentSkill {
  return {
    key: `builtin:${overrides.name}`,
    title: overrides.name,
    enabled: true,
    source: 'builtin',
    scope: '',
    editable: false,
    version: 0,
    ...overrides,
  }
}

describe('slash 菜单（build/filter/query）', () => {
  const skills: AgentSkill[] = [
    skill({ name: 'web-research', description: '联网搜索' }),
    skill({ name: 'deadline-queries', description: '期限查询' }),
    skill({ name: 'off-skill', description: '已停用', enabled: false }),
    skill({
      key: 'skill:8f3a',
      name: 'contract-review',
      description: '合同审查三段式',
      source: 'user',
      scope: 'lawyer',
      editable: true,
      version: 3,
    }),
  ]

  it('构建：命令在前、技能只列启用的；无会话时 compact 禁用、manage-skills 仍可用', () => {
    const items = buildSlashMenuItems(skills, false)
    expect(items[0]?.kind).toBe('command')
    expect(items[0]?.disabled).toBe(true)
    expect(items[0]?.disabledHint).toBe('先开始对话')
    // 「管理技能」不依赖会话：没有对话时律师也要能进去建技能
    const manage = items.find((i) => i.id === 'manage-skills')
    expect(manage?.kind).toBe('command')
    expect(manage?.disabled).toBeUndefined()
    expect(items.filter((i) => i.kind === 'skill').map((i) => i.id)).toEqual(['web-research', 'deadline-queries', 'contract-review'])
    expect(buildSlashMenuItems(skills, true)[0]?.disabled).toBeUndefined()
  })

  it('技能项带来源徽标：个人「我的」、内置「系统」；命令项无徽标', () => {
    const items = buildSlashMenuItems(skills, true)
    const badgeOf = (id: string) => items.find((i) => i.id === id)?.badge
    expect(badgeOf('contract-review')).toBe('我的')
    expect(badgeOf('web-research')).toBe('系统')
    expect(badgeOf('compact')).toBeUndefined()
    expect(badgeOf('manage-skills')).toBeUndefined()
  })

  it('列表 key 用技能身份（key）而非名字：个人与内置同名时不会撞 key', () => {
    const items = buildSlashMenuItems(
      [
        skill({ name: 'contract-review', description: '内置同名' }),
        skill({ key: 'skill:aa11', name: 'contract-review', description: '我的同名', source: 'user', scope: 'lawyer', editable: true, version: 1 }),
      ],
      true,
    )
    const keys = items.map((i) => i.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('过滤：子串匹配名与描述；skill: 前缀只挑技能', () => {
    const items = buildSlashMenuItems(skills, true)
    // 「期限」同时命中 deadline-queries 的描述与 compact 的描述（保留…期限等锚点）
    expect(filterSlashMenuItems(items, '期限').map((i) => i.id)).toEqual(['compact', 'deadline-queries'])
    expect(filterSlashMenuItems(items, 'web').map((i) => i.id)).toEqual(['web-research'])
    expect(filterSlashMenuItems(items, 'skill:dead').map((i) => i.id)).toEqual(['deadline-queries'])
    expect(filterSlashMenuItems(items, 'skill:')).toHaveLength(3)
    expect(filterSlashMenuItems(items, '不存在的词')).toEqual([])
  })

  it('过滤：中文「管理」能命中 manage-skills（命令标签可搜）', () => {
    const items = buildSlashMenuItems(skills, true)
    expect(filterSlashMenuItems(items, '管理').map((i) => i.id)).toEqual(['manage-skills'])
    // 前缀路径不参与命令筛选：`/skill:管理` 只挑技能，命令不出现在候选里
    expect(filterSlashMenuItems(items, 'skill:管理')).toEqual([])
  })

  it('触发条件：/ 打头才弹、多行/普通文本不弹', () => {
    expect(slashMenuQuery('/')).toBe('')
    expect(slashMenuQuery('/dead')).toBe('dead')
    expect(slashMenuQuery('你好')).toBeNull()
    expect(slashMenuQuery('/第一行\n第二行')).toBeNull()
  })
})
