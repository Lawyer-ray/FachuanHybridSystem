import { cloneTree, findByKey, newDeliverableId, type PhaseNode } from './special-phase-tree'

/**
 * 交付物的增删（按稳定 id，不用数组下标）。
 *
 * 下标在阶段重排、升降级、改名之后全部失效——原型里按 (阶段名, 下标) 打开编辑器，
 * 重排后会打开错的文件（README 第十三节的实测故障）。
 */

/** 加一份计划中的交付物（无文件、待起草） */
export function addDeliverable(tree: PhaseNode[], key: string, name: string): PhaseNode[] {
  const trimmed = name.trim()
  if (!trimmed) return tree
  const doc = /^《/.test(trimmed) ? trimmed : `《${trimmed.replace(/^《|》$/g, '')}》`
  const t = cloneTree(tree)
  const hit = findByKey(t, key)
  if (!hit) return tree
  hit.node.deliverables = [
    ...hit.node.deliverables,
    { id: newDeliverableId(), date: '', name: doc, version: '', state: 'todo', planned: true },
  ]
  return t
}

/** 删一份交付物（按 id，不用下标） */
export function removeDeliverable(tree: PhaseNode[], key: string, id: string): PhaseNode[] {
  const t = cloneTree(tree)
  const hit = findByKey(t, key)
  if (!hit) return tree
  hit.node.deliverables = hit.node.deliverables.filter((d) => d.id !== id)
  return t
}
