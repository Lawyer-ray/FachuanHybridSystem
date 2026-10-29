import { describe, expect, it } from 'vitest'

import {
  MAX_DEPTH,
  appendPhase,
  blankPhase,
  findByKey,
  flattenTree,
  indentPhase,
  insertAfter,
  moveBy,
  normalizeTree,
  outdentPhase,
  parentOf,
  patchPhase,
  removePhase,
  renamePhase,
  toggleOpen,
  type PhaseNode,
} from './special-phase-tree'

/** 造一个带层级的测试树：1 尽职调查 / 2 文件起草[2.1 职工安置] / 3 登记与注销 */
function tree(): PhaseNode[] {
  const a = { ...blankPhase('尽职调查'), key: 'a' }
  const c1 = { ...blankPhase('职工安置'), key: 'c1' }
  const c = { ...blankPhase('文件起草'), key: 'c', folders: [c1] }
  const d = { ...blankPhase('登记与注销'), key: 'd' }
  return [a, c, d]
}

describe('normalizeTree：编号与层级由结构推导', () => {
  it('先序遍历给出 path / depth / 编号（1 / 2 / 2.1 / 3）', () => {
    expect(flattenTree(tree()).map((x) => [x.no, x.depth, x.node.name])).toEqual([
      ['1', 1, '尽职调查'],
      ['2', 1, '文件起草'],
      ['2.1', 2, '职工安置'],
      ['3', 1, '登记与注销'],
    ])
  })

  it('超过 3 级的层级在入口处被丢弃（页面表达不了 4 级）', () => {
    const deep = normalizeTree([
      { name: 'L1', folders: [{ name: 'L2', folders: [{ name: 'L3', folders: [{ name: 'L4' }] }] }] },
    ])
    expect(flattenTree(deep).map((x) => x.node.name)).toEqual(['L1', 'L2', 'L3'])
    expect(flattenTree(deep).length).toBe(MAX_DEPTH)
  })

  it('缺 key 时补稳定 key，缺名字时给占位名', () => {
    const t = normalizeTree([{}])
    expect(t[0]?.key).toMatch(/^ph_/)
    expect(t[0]?.name).toBe('未命名阶段')
  })
})

describe('indent / outdent：层级编辑', () => {
  it('降级 = 挂到前一个同级节点下', () => {
    const r = indentPhase(tree(), 'c')
    expect(r.ok).toBe(true)
    const flat = flattenTree(r.tree)
    expect(flat.map((x) => [x.no, x.node.name])).toEqual([
      ['1', '尽职调查'],
      ['1.1', '文件起草'],
      ['1.1.1', '职工安置'],
      ['2', '登记与注销'],
    ])
  })

  it('第一个节点不能降级（前面没有「哥哥」可挂靠）', () => {
    const r = indentPhase(tree(), 'a')
    expect(r.ok).toBe(false)
    expect(r.reason).toContain('前面没有同级阶段')
  })

  it('第 3 级不能再降级', () => {
    const t = indentPhase(tree(), 'c').tree // 文件起草 → 1.1，职工安置 → 1.1.1（第 3 级）
    const r = indentPhase(t, 'c1')
    expect(r.ok).toBe(false)
    expect(r.reason).toContain(`${MAX_DEPTH}`)
  })

  it('升级 = 提到父节点之后，原位置的后续兄弟跟着变成它的子节点', () => {
    const t: PhaseNode[] = [
      { ...blankPhase('父'), key: 'p', folders: [
        { ...blankPhase('子1'), key: 'k1' },
        { ...blankPhase('子2'), key: 'k2' },
      ] },
      { ...blankPhase('尾'), key: 'z' },
    ]
    const r = outdentPhase(t, 'k1')
    expect(r.ok).toBe(true)
    expect(flattenTree(r.tree).map((x) => [x.no, x.node.name])).toEqual([
      ['1', '父'],
      ['2', '子1'],
      ['2.1', '子2'],
      ['3', '尾'],
    ])
  })

  it('第 1 级不能升级', () => {
    expect(outdentPhase(tree(), 'a')).toMatchObject({ ok: false, reason: '已经是第 1 级' })
  })

  it('parentOf 能取到二级节点的父节点（路径第一段是根层下标，不是 children 下标）', () => {
    expect(parentOf(tree(), 'c1')?.node.name).toBe('文件起草')
    expect(parentOf(tree(), 'a')).toBeNull()
  })
})

describe('moveBy / removePhase / rename / toggle', () => {
  it('同级上移下移，越界返回原树', () => {
    expect(flattenTree(moveBy(tree(), 'd', -1)).map((x) => x.node.name)).toEqual([
      '尽职调查',
      '登记与注销',
      '文件起草',
      '职工安置',
    ])
    expect(moveBy(tree(), 'a', -1)).toEqual(tree())
    expect(moveBy(tree(), 'd', 1)).toEqual(tree())
  })

  it('删除节点连同子树（父节点删掉，子节点一起走）', () => {
    expect(flattenTree(removePhase(tree(), 'c')).map((x) => x.node.name)).toEqual(['尽职调查', '登记与注销'])
  })

  it('改名不动 key，也不动交付物归属', () => {
    const next = renamePhase(tree(), 'c', '文件起草与定稿')
    expect(findByKey(next, 'c')?.node.name).toBe('文件起草与定稿')
    expect(findByKey(next, 'c1')?.node.name).toBe('职工安置')
  })

  it('折叠态存回节点（重绘后保留）', () => {
    const next = toggleOpen(tree(), 'c')
    expect(findByKey(next, 'c')?.node.open).toBe(true)
    expect(findByKey(tree(), 'c')?.node.open).toBe(false)
  })

  it('结构操作不改入参', () => {
    const t = tree()
    const snapshot = JSON.stringify(t)
    renamePhase(t, 'c', 'x')
    removePhase(t, 'c')
    moveBy(t, 'd', -1)
    expect(JSON.stringify(t)).toBe(snapshot)
  })

  it('insertAfter / appendPhase / patchPhase 都产出新树', () => {
    const t = insertAfter(tree(), 'a', blankPhase('方案设计'))
    expect(flattenTree(t).map((x) => x.node.name)).toEqual(['尽职调查', '方案设计', '文件起草', '职工安置', '登记与注销'])
    expect(flattenTree(appendPhase(t, blankPhase('交割'))).at(-1)?.node.name).toBe('交割')
    expect(findByKey(patchPhase(t, 'a', { acceptance: '尽调报告定稿' }), 'a')?.node.acceptance).toBe('尽调报告定稿')
  })
})
