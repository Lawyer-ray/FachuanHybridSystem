/**
 * 阶段树的**只读遍历**（查节点、算编号、找父节点）。
 *
 * 与 `phase-tree-ops.ts` 分开：遍历不产生新树、不改任何东西，结构操作则一律
 * 「先 clone 再改」。两件混在一个文件里时，读代码的人要先判断「这个函数会不会
 * 动我的树」——按副作用边界切开后就不用判断了。树的类型与构造在 `phase-tree.ts`。
 */

import type { PhaseNode } from './phase-tree'

/** 先序遍历（先父后子），回调拿索引路径 */
export function walk(tree: PhaseNode[], fn: (node: PhaseNode, path: number[]) => void, path: number[] = []): void {
  tree.forEach((n, i) => {
    const here = [...path, i]
    fn(n, here)
    if (n.folders.length > 0) walk(n.folders, fn, here)
  })
}

export interface FlatPhase {
  node: PhaseNode
  /** 根到该节点的索引路径 */
  path: number[]
  /** 层级（1 起） */
  depth: number
  /** 编号 `1` / `3.1` / `3.1.2`，由路径推导 */
  no: string
}

/** 先序遍历 → 扁平列表（渲染与单测都只吃这个） */
export function flattenTree(tree: PhaseNode[]): FlatPhase[] {
  const out: FlatPhase[] = []
  walk(tree, (node, path) => {
    out.push({
      node,
      path,
      depth: path.length,
      no: path.map((i) => i + 1).join('.'),
    })
  })
  return out
}

export function findByKey(tree: PhaseNode[], key: string): { node: PhaseNode; path: number[] } | null {
  let hit: { node: PhaseNode; path: number[] } | null = null
  walk(tree, (node, path) => {
    if (node.key === key) hit = { node, path }
  })
  return hit
}

/**
 * 父节点（根层返回 null）。
 *
 * **路径第一段是根层下标，必须先在 tree 上取一次**，再从第二段起在 folders 上走。
 * 原型里直接从 tree 开始循环、把 path[0] 当下标取 folders[0]，三级节点的
 * parentOf 返回 {node: undefined}——这是实测踩过的坑（README 第十三节 bug 1）。
 */
export function parentOf(tree: PhaseNode[], key: string): { node: PhaseNode; path: number[] } | null {
  const hit = findByKey(tree, key)
  if (!hit || hit.path.length < 2) return null
  const parentPath = hit.path.slice(0, -1)
  let node = tree[parentPath[0] ?? 0]
  if (!node) return null
  for (let i = 1; i < parentPath.length; i += 1) {
    const next: PhaseNode | undefined = node.folders[parentPath[i] ?? 0]
    if (!next) return null
    node = next
  }
  return { node, path: parentPath }
}

/** 路径末端下标（`path` 由 walk 产出，恒非空） */
export function last(path: number[]): number {
  return path[path.length - 1] ?? 0
}

/** 节点的存放容器（根层就是 tree 本身，否则是父节点的 folders） */
export function siblingsOf(tree: PhaseNode[], key: string): PhaseNode[] {
  const par = parentOf(tree, key)
  return par ? par.node.folders : tree
}
