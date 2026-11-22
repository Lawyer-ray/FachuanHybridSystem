/**
 * 阶段树的**结构操作**（移动 / 增删 / 升降级 / 改名 / 展开态）。
 *
 * 每个函数都是纯函数：先 `cloneTree` 再改，**入参树不被污染**，调用方拿到的是
 * 新树（React 靠这一点判断要不要重渲染）。查节点/算编号的原语在
 * `phase-tree-query.ts`，树的类型与构造在 `phase-tree.ts`。
 */

import { cloneTree, MAX_DEPTH, type PhaseNode } from './phase-tree'
import { findByKey, last, parentOf, siblingsOf } from './phase-tree-query'

/**
 * 把 src 移到 dst 的**前/后**（同级）。
 *
 * 拖拽排序与上移下移共用的唯一原语：「先摘出，再插到目标同级」。只实现一次，
 * 避免上移/下移/拖拽三套逻辑各自算下标而互相错位。
 */
export function moveBefore(tree: PhaseNode[], srcKey: string, dstKey: string, after: boolean): PhaseNode[] {
  if (srcKey === dstKey) return tree
  const src = findByKey(tree, srcKey)
  const dst = findByKey(tree, dstKey)
  if (!src || !dst) return tree
  // 不能移进自己的子孙（否则子树自我嵌套，遍历死循环）
  const intoOwnSubtree =
    dst.path.length > src.path.length && src.path.every((v, i) => dst.path[i] === v)
  if (intoOwnSubtree) return tree

  const t = cloneTree(tree)
  const srcNow = findByKey(t, srcKey)
  if (!srcNow) return tree
  const [node] = siblingsOf(t, srcKey).splice(last(srcNow.path), 1)
  if (!node) return tree
  const dstNow = findByKey(t, dstKey)
  if (!dstNow) return tree
  siblingsOf(t, dstKey).splice(last(dstNow.path) + (after ? 1 : 0), 0, node)
  return t
}

/** 同级上移 / 下移 delta 位（越界返回原树） */
export function moveBy(tree: PhaseNode[], key: string, delta: number): PhaseNode[] {
  const hit = findByKey(tree, key)
  if (!hit) return tree
  const sib = siblingsOf(tree, key)
  const target = sib[last(hit.path) + delta]
  if (!target) return tree
  return moveBefore(tree, key, target.key, delta > 0)
}

/** 在 key 之后（或之前）插入同层新节点 */
export function insertAfter(tree: PhaseNode[], key: string, node: PhaseNode, after = true): PhaseNode[] {
  const t = cloneTree(tree)
  const hit = findByKey(t, key)
  if (!hit) {
    t.push(node)
    return t
  }
  siblingsOf(t, key).splice(last(hit.path) + (after ? 1 : 0), 0, node)
  return t
}

/** 追加到根层末尾 */
export function appendPhase(tree: PhaseNode[], node: PhaseNode): PhaseNode[] {
  return [...cloneTree(tree), node]
}

/** 追加为某节点的子阶段（已到 MAX_DEPTH 时拒绝） */
export function appendChild(tree: PhaseNode[], parentKey: string, node: PhaseNode): PhaseNode[] {
  const hit = findByKey(tree, parentKey)
  if (!hit || hit.path.length >= MAX_DEPTH) return tree
  const t = cloneTree(tree)
  const target = findByKey(t, parentKey)
  if (!target) return tree
  target.node.folders.push(node)
  return t
}

/** 删除节点（连同子树） */
export function removePhase(tree: PhaseNode[], key: string): PhaseNode[] {
  const hit = findByKey(tree, key)
  if (!hit) return tree
  const t = cloneTree(tree)
  const now = findByKey(t, key)
  if (!now) return tree
  siblingsOf(t, key).splice(last(now.path), 1)
  return t
}

export interface TreeOpResult {
  tree: PhaseNode[]
  ok: boolean
  /** 拒绝原因（直接进 toast，不吞掉） */
  reason?: string
}

/**
 * 降级：变成**前一个兄弟的子节点**。
 *
 * 没有前一个兄弟就不能降级——第一个节点下面挂不了东西，它得先有个「哥哥」。
 */
export function indentPhase(tree: PhaseNode[], key: string): TreeOpResult {
  const hit = findByKey(tree, key)
  if (!hit) return { tree, ok: false, reason: '找不到该阶段' }
  if (hit.path.length >= MAX_DEPTH) return { tree, ok: false, reason: `最多 ${MAX_DEPTH} 级` }
  if (last(hit.path) === 0) return { tree, ok: false, reason: '前面没有同级阶段可以挂靠' }
  const t = cloneTree(tree)
  const now = findByKey(t, key)
  if (!now) return { tree, ok: false, reason: '找不到该阶段' }
  const arr = siblingsOf(t, key)
  const at = last(now.path)
  const prev = arr[at - 1]
  const [node] = arr.splice(at, 1)
  if (!prev || !node) return { tree, ok: false, reason: '前面没有同级阶段可以挂靠' }
  prev.folders.push(node)
  return { tree: t, ok: true }
}

/**
 * 升级：升到父节点之后（成为父节点的兄弟）。
 *
 * 原位置的后续兄弟跟着变成它的子节点——否则升级一个带子节点的父节点会把自己
 * 的孩子留在原处，变成「孩子挂在叔叔下面」，与直觉相反。
 */
export function outdentPhase(tree: PhaseNode[], key: string): TreeOpResult {
  const hit = findByKey(tree, key)
  if (!hit) return { tree, ok: false, reason: '找不到该阶段' }
  if (hit.path.length <= 1) return { tree, ok: false, reason: '已经是第 1 级' }

  const t = cloneTree(tree)
  const now = findByKey(t, key)
  const par = parentOf(t, key)
  if (!now || !par) return { tree, ok: false, reason: '找不到该阶段' }
  const i = last(now.path)
  // 兄弟数组就是父节点的 folders（同一引用），只操作这一个数组
  const arr = par.node.folders
  const [node] = arr.splice(i, 1)
  if (!node) return { tree, ok: false, reason: '找不到该阶段' }
  const followers = arr.splice(i)
  node.folders = node.folders.concat(followers)

  // 插到「父节点之后」= 父节点在祖父层的位置 + 1（父节点不在当前这层数组里）
  const grand = parentOf(t, par.node.key)
  if (!grand) {
    t.splice(t.indexOf(par.node) + 1, 0, node)
  } else {
    const gArr = grand.node.folders
    gArr.splice(gArr.indexOf(par.node) + 1, 0, node)
  }
  return { tree: t, ok: true }
}

/** 改名（key 稳定 → 交付物不丢） */
export function renamePhase(tree: PhaseNode[], key: string, name: string): PhaseNode[] {
  return patchPhase(tree, key, { name })
}

/** 改任意字段（改名 / 验收标准 / 展开态 / 开始日 / 模板） */
export function patchPhase(tree: PhaseNode[], key: string, fields: Partial<PhaseNode>): PhaseNode[] {
  const t = cloneTree(tree)
  const hit = findByKey(t, key)
  if (!hit) return tree
  Object.assign(hit.node, fields)
  return t
}

/** 切换展开态（折叠/展开写回节点，重绘后保留） */
export function toggleOpen(tree: PhaseNode[], key: string): PhaseNode[] {
  const hit = findByKey(tree, key)
  if (!hit) return tree
  return patchPhase(tree, key, { open: !hit.node.open })
}
