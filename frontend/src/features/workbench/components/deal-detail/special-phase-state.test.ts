import { describe, expect, it } from 'vitest'

import { addDeliverable, removeDeliverable } from './special-phase-crud'
import {
  deliverableStateLabel,
  derivePhaseStates,
  phaseMetaText,
  phaseStateLabel,
  treeStats,
} from './special-phase-state'
import { blankPhase, findByKey, flattenTree, folderNameOf, type PhaseDeliverable, type PhaseNode } from './special-phase-tree'

/** 实际文件（非计划项）：状态 ok=定稿 / doing=撰写中 */
function file(name: string, state: 'ok' | 'doing' = 'ok'): PhaseDeliverable {
  return { id: `f:${name}`, date: '2026-10-29', name, version: 'v1', state, subpath: `p/${name}`, planned: false }
}

/** 固定 key（= 名字）：各用例自己造树时不必先 flatten 再取 key */
function node(name: string, deliverables: PhaseDeliverable[] = [], folders: PhaseNode[] = []): PhaseNode {
  return { ...blankPhase(name), key: name, deliverables, folders }
}

describe('derivePhaseStates：有文件=已完成 / 第一个空叶子=进行中 / 其后=未开始', () => {
  it('父节点由子节点聚合，当前节点是第一个没有实际文件的叶子', () => {
    const tree = [
      node('尽调', [file('《尽调报告》')]),
      node('文件起草', [], [node('职工安置', [file('《安置方案》', 'doing')]), node('债权债务')]),
      node('登记与注销'),
    ]
    const states = flattenTree(derivePhaseStates(tree)).map((x) => [x.node.name, x.node.state])
    expect(states).toEqual([
      ['尽调', 'done'],
      ['文件起草', 'doing'],
      ['职工安置', 'done'],
      ['债权债务', 'doing'],
      ['登记与注销', 'todo'],
    ])
  })

  it('计划中的交付物不算「已完成」', () => {
    const tree = [node('尽调', [{ id: 'p1', date: '', name: '《清单》', version: '', state: 'todo', planned: true }])]
    expect(derivePhaseStates(tree)[0]?.state).toBe('doing')
  })

  it('父节点排在自己子节点之前，也不会抢走「进行中」', () => {
    const tree = [node('父', [], [node('子一', [file('《a》')]), node('子二')])]
    const flat = flattenTree(derivePhaseStates(tree))
    expect(flat.map((x) => [x.node.name, x.node.state])).toEqual([
      ['父', 'doing'],
      ['子一', 'done'],
      ['子二', 'doing'],
    ])
  })
})

describe('treeStats / 文案', () => {
  it('统计总阶段、已完成、实际交付物数', () => {
    const tree = derivePhaseStates([node('a', [file('《a》')]), node('b', [], [node('b1', [file('《b》')]), node('b2')])])
    // a 与 b1 有实际文件=已完成；b2 是第一个空叶子=进行中；b 由子聚合=进行中
    expect(treeStats(tree)).toEqual({ total: 4, done: 2, docs: 2 })
  })

  it('阶段与交付物状态文案（计划项是「待起草」）', () => {
    expect(phaseStateLabel('done')).toBe('已完成')
    expect(phaseStateLabel(undefined)).toBe('未开始')
    expect(deliverableStateLabel(file('《x》', 'doing'))).toBe('撰写中')
    expect(
      deliverableStateLabel({ id: 'p', date: '', name: '《x》', version: '', state: 'todo', planned: true }),
    ).toBe('待起草')
  })

  it('元信息三种情况严格分开，尾巴不挂多余分隔符', () => {
    expect(phaseMetaText(2, 3)).toBe('2 个子阶段 · 3 个文件')
    expect(phaseMetaText(2, 0)).toBe('2 个子阶段')
    expect(phaseMetaText(0, 3)).toBe('3 个文件')
    expect(phaseMetaText(0, 0)).toBe('空')
  })
})

describe('folderNameOf：合同文件夹目录名由阶段树派生', () => {
  it('`<编号>-<阶段名>`，子阶段带 `3.1-` 前缀；改名后同步', () => {
    const tree = [node('尽调'), node('文件起草', [], [node('职工安置文书')])]
    expect(flattenTree(tree).map(folderNameOf)).toEqual(['1-尽调', '2-文件起草', '2.1-职工安置文书'])
  })
})

describe('交付物增删（按稳定 id，不用下标）', () => {
  it('新增自动补书名号，落为「待起草」的计划项', () => {
    const next = addDeliverable([node('起草')], '起草', '职工安置方案')
    const doc = next[0]?.deliverables[0]
    expect(doc?.name).toBe('《职工安置方案》')
    expect(doc?.planned).toBe(true)
    expect(doc?.state).toBe('todo')
  })

  it('已带书名号不重复包；空名不新增', () => {
    expect(addDeliverable([node('起草')], '起草', '《方案》')[0]?.deliverables[0]?.name).toBe('《方案》')
    expect(addDeliverable([node('起草')], '起草', '   ')[0]?.deliverables).toEqual([])
  })

  it('按 id 删除，重排后仍删得对', () => {
    const a = addDeliverable([node('起草')], '起草', '甲')
    const b = addDeliverable(a, '起草', '乙')
    const targetId = findByKey(b, '起草')!.node.deliverables[0]!.id
    const next = removeDeliverable(b, '起草', targetId)
    expect(findByKey(next, '起草')?.node.deliverables.map((d) => d.name)).toEqual(['《乙》'])
  })
})
