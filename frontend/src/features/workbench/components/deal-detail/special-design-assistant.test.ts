import { describe, expect, it } from 'vitest'

import { createRuleAssistant } from './special-design-assistant'
import { blankPhase, flattenTree, type PhaseNode } from './special-phase-tree'

/** 关厂清盘的起点骨架（与演示数据同形：文件起草下挂两个子阶段） */
function draft(): PhaseNode[] {
  return [
    { ...blankPhase('尽职调查'), key: 'p1' },
    { ...blankPhase('方案设计'), key: 'p2' },
    {
      ...blankPhase('文件起草'),
      key: 'p3',
      acceptance: '三件核心文书定稿',
      deliverables: [
        { id: 'd1', date: '', name: '《职工安置方案》', version: '', state: 'todo', planned: true },
      ],
      folders: [
        { ...blankPhase('职工安置文书'), key: 'p31' },
        { ...blankPhase('债权债务与决议'), key: 'p32' },
      ],
    },
    { ...blankPhase('登记与注销'), key: 'p4', acceptance: '30 天内完成市场监管注销登记' },
    { ...blankPhase('交割与移交'), key: 'p5' },
  ]
}

const assistant = createRuleAssistant()
const ask = (text: string, tree: PhaseNode[] = draft(), selectedKey: string | null = null) =>
  assistant.suggest({ text, draft: tree, selectedKey })

describe('AI 设计：多轮对话改的是草稿，并如实回报改了哪几处', () => {
  it('「职工安置单独拆一步」→ 在文件起草之后插入独立阶段，并把同名交付物移过来', () => {
    const turn = ask('这家厂 120 名职工，先把职工安置单独拆一个阶段')
    expect(turn.unchanged).toBe(false)
    expect(turn.changes).toHaveLength(1)
    expect(turn.changes[0]).toContain('职工安置')
    const names = flattenTree(turn.draft).filter((x) => x.depth === 1).map((x) => x.node.name)
    expect(names).toEqual(['尽职调查', '方案设计', '文件起草', '职工安置', '登记与注销', '交割与移交'])
    // 原阶段里重复的《职工安置方案》被摘走（落在新阶段里由规则自己带）
    const drafting = turn.draft.find((n) => n.name === '文件起草')
    expect(drafting?.deliverables.map((d) => d.name)).toEqual([])
  })

  it('顶层已有「职工安置」时不重复拆（子层同名细项不阻止拆分）', () => {
    const once = ask('职工安置单独拆一步').draft
    const twice = ask('职工安置单独拆一步', once)
    expect(twice.unchanged).toBe(true)
    expect(twice.draft).toBe(once)
  })

  it('「第 3 步再拆细」→ 按阶段语义给两个有意义的子步骤，不是编号占位', () => {
    const turn = ask('第 3 步再拆细一点，把清税申报单列', draft())
    expect(turn.changes[0]).toContain('拆成两步')
    const names = flattenTree(turn.draft).map((x) => x.node.name)
    expect(names).toContain('核心文书起草')
    expect(names).toContain('股东决议与定稿')
  })

  it('「验收标准别写死天数」→ 清掉具体天数并说明清了几处', () => {
    const turn = ask('验收标准都别写具体天数')
    expect(turn.changes[0]).toContain('清掉 1 处')
    expect(turn.draft.find((n) => n.name === '登记与注销')?.acceptance).not.toMatch(/\d+\s*天/)
  })

  it('「加一个阶段」→ 末尾追加；「删掉登记与注销」→ 删除该阶段', () => {
    const added = ask('加一个阶段')
    expect(flattenTree(added.draft).at(-1)?.node.name).toBe('归档与复盘')
    const removed = ask('删掉登记与注销阶段')
    expect(removed.draft.map((n) => n.name)).not.toContain('登记与注销')
  })

  it('「补一份交付物」落到右栏选中的阶段', () => {
    const turn = ask('给这个阶段补一份交付物', draft(), 'p2')
    const p2 = turn.draft.find((n) => n.key === 'p2')
    expect(p2?.deliverables.map((d) => d.name)).toEqual(['《方案设计工作底稿》'])
  })

  it('没命中时**明确说没找到**，且草稿原样不动', () => {
    const tree = draft()
    const turn = ask('帮我看看这份合同有什么风险', tree)
    expect(turn.unchanged).toBe(true)
    expect(turn.changes).toEqual([])
    expect(turn.draft).toBe(tree)
    expect(turn.reply).toContain('没找到可执行的改动')
  })

  it('多轮串起来：第二句作用在第一句改完的草稿上', () => {
    const first = ask('职工安置单独拆一步')
    const second = ask('验收标准都别写具体天数', first.draft)
    expect(second.draft).not.toBe(first.draft)
    expect(flattenTree(second.draft).map((x) => x.node.name)).toContain('职工安置')
  })
})
