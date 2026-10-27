import { describe, expect, it } from 'vitest'

import { buildSlashMenuItems, filterSlashMenuItems, slashMenuQuery } from './slash'

describe('slash 菜单（build/filter/query）', () => {
  const skills = [
    { name: 'web-research', description: '联网搜索', enabled: true },
    { name: 'deadline-queries', description: '期限查询', enabled: true },
    { name: 'off-skill', description: '已停用', enabled: false },
  ]

  it('构建：命令在前、技能只列启用的；无会话时 compact 禁用', () => {
    const items = buildSlashMenuItems(skills, false)
    expect(items[0]?.kind).toBe('command')
    expect(items[0]?.disabled).toBe(true)
    expect(items[0]?.disabledHint).toBe('先开始对话')
    expect(items.filter((i) => i.kind === 'skill').map((i) => i.id)).toEqual(['web-research', 'deadline-queries'])
    expect(buildSlashMenuItems(skills, true)[0]?.disabled).toBeUndefined()
  })

  it('过滤：子串匹配名与描述；skill: 前缀只挑技能', () => {
    const items = buildSlashMenuItems(skills, true)
    // 「期限」同时命中 deadline-queries 的描述与 compact 的描述（保留…期限等锚点）
    expect(filterSlashMenuItems(items, '期限').map((i) => i.id)).toEqual(['compact', 'deadline-queries'])
    expect(filterSlashMenuItems(items, 'web').map((i) => i.id)).toEqual(['web-research'])
    expect(filterSlashMenuItems(items, 'skill:dead').map((i) => i.id)).toEqual(['deadline-queries'])
    expect(filterSlashMenuItems(items, 'skill:')).toHaveLength(2)
    expect(filterSlashMenuItems(items, '不存在的词')).toEqual([])
  })

  it('触发条件：/ 打头才弹、多行/普通文本不弹', () => {
    expect(slashMenuQuery('/')).toBe('')
    expect(slashMenuQuery('/dead')).toBe('dead')
    expect(slashMenuQuery('你好')).toBeNull()
    expect(slashMenuQuery('/第一行\n第二行')).toBeNull()
  })
})
