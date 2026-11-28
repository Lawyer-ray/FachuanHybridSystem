import { describe, expect, it } from 'vitest'

import type { AgentSkill } from '../types'
import { buildSlashMenuItems, filterSlashMenuItems, slashMenuQuery } from './slash'

/**
 * 技能清单项（CONTRACT §2 的完整字段集）。测试只关心 name/title/source/enabled/
 * effective，其余给「内置技能」的缺省值；每处按需覆盖。
 */
function skill(overrides: Partial<AgentSkill> & Pick<AgentSkill, 'name' | 'description'>): AgentSkill {
  return {
    key: `builtin:${overrides.name}`,
    title: overrides.name,
    enabled: true,
    source: 'builtin',
    scope: 'builtin',
    scope_weight: -1,
    editable: false,
    version: 0,
    status: 'active',
    review_status: 'none',
    review_note: '',
    published_version: 0,
    has_unpublished_changes: false,
    shadowed: [],
    effective: true,
    shadowed_by: null,
    can_edit: false,
    can_submit: false,
    can_review: false,
    can_archive: false,
    can_restore: false,
    ...overrides,
  }
}

/** 个人技能的缺省值（`source` 是交付面的说法、`scope` 是层级，两者同一条命的两面） */
function mine(overrides: Partial<AgentSkill> & Pick<AgentSkill, 'name' | 'description'>): AgentSkill {
  return skill({
    key: `skill:${overrides.name}`,
    source: 'user',
    scope: 'lawyer',
    scope_weight: 0,
    editable: true,
    can_edit: true,
    ...overrides,
  })
}

describe('slash 菜单（build/filter/query）', () => {
  const skills: AgentSkill[] = [
    skill({ name: 'web-research', description: '联网搜索' }),
    skill({ name: 'deadline-queries', description: '期限查询' }),
    skill({ name: 'off-skill', description: '已停用', enabled: false }),
    mine({ name: 'contract-review', description: '合同审查三段式', version: 3 }),
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

  it('来源徽标覆盖四层：团队「团队」、所内「所内」', () => {
    const items = buildSlashMenuItems(
      [
        skill({ name: 'firm-checklist', description: '所内清单', source: 'law_firm', scope: 'law_firm', scope_weight: 2 }),
        skill({ name: 'team-checklist', description: '团队清单', source: 'team', scope: 'team', scope_weight: 1 }),
      ],
      true,
    )
    expect(items.find((i) => i.id === 'firm-checklist')?.badge).toBe('所内')
    expect(items.find((i) => i.id === 'team-checklist')?.badge).toBe('团队')
  })

  it('被遮蔽（effective=false）与已下线的技能不进菜单', () => {
    const items = buildSlashMenuItems(
      [
        mine({ name: 'contract-review', description: '我的同名（赢家）' }),
        // 同名的所内条目被「我的」顶掉：`/skill:contract-review` 展开的是我的正文，
        // 把它也列出来会让徽标（所内）与正文（我的）对不上
        skill({
          key: 'skill:firm-1',
          name: 'contract-review',
          description: '所内同名（被遮蔽）',
          source: 'law_firm',
          scope: 'law_firm',
          scope_weight: 2,
          effective: false,
          shadowed_by: { key: 'skill:contract-review', scope: 'lawyer', title: '合同审查' },
        }),
        skill({ name: 'archived-skill', description: '已下线', effective: false }),
      ],
      true,
    )
    expect(items.filter((i) => i.kind === 'skill').map((i) => i.key)).toEqual(['skill-skill:contract-review'])
  })

  it('列表 key 用技能身份（key）而非名字：个人与内置同名时不会撞 key', () => {
    const items = buildSlashMenuItems(
      [
        skill({ name: 'contract-review', description: '内置同名' }),
        mine({ name: 'contract-review', description: '我的同名', version: 1 }),
      ],
      true,
    )
    const keys = items.map((i) => i.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('技能项保留中文 title；命令项没有 title', () => {
    const items = buildSlashMenuItems([skill({ name: 'contract-review', title: '合同审查三段式', description: '按四段核对' })], true)
    expect(items.find((i) => i.id === 'contract-review')?.title).toBe('合同审查三段式')
    // `title` 只属于技能项：命令没有中文显示名这一说法
    expect(items.find((i) => i.id === 'compact')?.title).toBeUndefined()
  })

  it('过滤：按中文 title 能搜到（不必背 slug），skill: 前缀同样生效', () => {
    const items = buildSlashMenuItems(
      [
        skill({ name: 'deadline-queries', title: '期限查询', description: 'deadline scan' }),
        skill({ name: 'contract-review', title: '合同审查三段式', description: 'review contract' }),
      ],
      true,
    )
    expect(filterSlashMenuItems(items, '审查').map((i) => i.id)).toEqual(['contract-review'])
    // compact 的描述里也有「期限」（保留案号/期限等锚点），所以它同被命中
    expect(filterSlashMenuItems(items, '期限').map((i) => i.id)).toEqual(['compact', 'deadline-queries'])
    // 用户已明确在挑技能时，中文名也要能挑
    expect(filterSlashMenuItems(items, 'skill:审查').map((i) => i.id)).toEqual(['contract-review'])
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
