/**
 * special-phase-crud：交付物增删（纯函数，node 环境）。
 *
 * 两个函数都按**稳定 key / id** 定位而不是数组下标——下标在重排、升降级、
 * 改名之后全部失效，按 (阶段名, 下标) 打开编辑器会打开错的文件。
 */
import { describe, expect, it } from 'vitest'

import { addDeliverable, removeDeliverable } from './special-phase-crud'
import { blankPhase, type PhaseDeliverable, type PhaseNode } from './special-phase-tree'

function deliverable(partial: Partial<PhaseDeliverable> = {}): PhaseDeliverable {
  return { id: 'd1', date: '', name: '《尽调报告》', version: '', state: 'ok', subpath: 'p/x.docx', planned: false, ...partial }
}

function tree(partial: { key: string; deliverables?: PhaseDeliverable[]; folders?: PhaseNode[] }): PhaseNode[] {
  return [{ ...blankPhase('尽职调查'), key: partial.key, deliverables: partial.deliverables ?? [], folders: partial.folders ?? [] }]
}

describe('addDeliverable：加一份计划中的交付物', () => {
  it('追加到目标阶段，并标记为 planned/todo、无文件', () => {
    const t = tree({ key: 'ph_a' })
    const next = addDeliverable(t, 'ph_a', '清算方案')
    expect(next[0]?.deliverables).toHaveLength(1)
    expect(next[0]?.deliverables[0]).toMatchObject({
      name: '《清算方案》',
      date: '',
      version: '',
      state: 'todo',
      planned: true,
    })
    expect(next[0]?.deliverables[0]?.subpath).toBeUndefined()
  })

  it('名字自动补书名号；已带书名号的不重复包', () => {
    const next = addDeliverable(tree({ key: 'ph_a' }), 'ph_a', '《清算方案》')
    expect(next[0]?.deliverables[0]?.name).toBe('《清算方案》')
  })

  it('名字首尾空白被裁掉后再判断书名号', () => {
    const next = addDeliverable(tree({ key: 'ph_a' }), 'ph_a', '  清算方案  ')
    expect(next[0]?.deliverables[0]?.name).toBe('《清算方案》')
  })

  it('空名字不加（返回原数组引用）', () => {
    const t = tree({ key: 'ph_a' })
    expect(addDeliverable(t, 'ph_a', '   ')).toBe(t)
    expect(addDeliverable(t, 'ph_a', '')).toBe(t)
  })

  it('找不到 key 时返回原数组引用', () => {
    const t = tree({ key: 'ph_a' })
    expect(addDeliverable(t, 'ph_missing', '清算方案')).toBe(t)
  })

  it('不改入参（返回新树）', () => {
    const t = tree({ key: 'ph_a' })
    const next = addDeliverable(t, 'ph_a', '清算方案')
    expect(t[0]?.deliverables).toHaveLength(0)
    expect(next).not.toBe(t)
  })

  it('能加到子阶段（按 key 任意层定位）', () => {
    const child = { ...blankPhase('职工安置'), key: 'ph_child', deliverables: [] }
    const t: PhaseNode[] = [{ ...blankPhase('主线'), key: 'ph_root', deliverables: [], folders: [child] }]
    const next = addDeliverable(t, 'ph_child', '安置方案')
    expect(next[0]?.folders[0]?.deliverables.map((d) => d.name)).toEqual(['《安置方案》'])
    expect(next[0]?.deliverables).toHaveLength(0)
  })
})

describe('removeDeliverable：按 id 删交付物', () => {
  it('只删指定 id，其余保留', () => {
    const t = tree({ key: 'ph_a', deliverables: [deliverable({ id: 'd1' }), deliverable({ id: 'd2', name: '《清算方案》' })] })
    const next = removeDeliverable(t, 'ph_a', 'd1')
    expect(next[0]?.deliverables.map((d) => d.id)).toEqual(['d2'])
  })

  it('id 不存在时树结构不变（但仍返回新树）', () => {
    const t = tree({ key: 'ph_a', deliverables: [deliverable({ id: 'd1' })] })
    const next = removeDeliverable(t, 'ph_a', 'd_missing')
    expect(next[0]?.deliverables.map((d) => d.id)).toEqual(['d1'])
    expect(next).not.toBe(t)
  })

  it('找不到 key 时返回原数组引用', () => {
    const t = tree({ key: 'ph_a', deliverables: [deliverable()] })
    expect(removeDeliverable(t, 'ph_missing', 'd1')).toBe(t)
  })

  it('不改入参', () => {
    const t = tree({ key: 'ph_a', deliverables: [deliverable({ id: 'd1' })] })
    removeDeliverable(t, 'ph_a', 'd1')
    expect(t[0]?.deliverables).toHaveLength(1)
  })
})
