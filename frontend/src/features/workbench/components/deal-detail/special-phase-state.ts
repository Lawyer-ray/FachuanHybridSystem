import {
  cloneTree,
  flattenTree,
  walk,
  type PhaseDeliverable,
  type PhaseNode,
  type PhaseState,
  type DeliverableState,
} from './special-phase-tree'

/**
 * 阶段状态：有**实际文件**的叶子 = 已完成（docx 撰写中按实际文件也算推进过）；
 * 第一个没有实际文件的**叶子** = 进行中；其余 = 未开始。
 *
 * 父节点的完成度只由子节点聚合——否则「父阶段已完成、子阶段还没开始」这种
 * 自相矛盾的展示必然出现（原型实测）。
 *
 * 「第一个未完成叶子」必须排除有子节点的父节点：先序里父节点排在子节点之前，
 * 不排除就会把 curKey 抢走，真正的当前叶子被判成未开始。
 */
export function derivePhaseStates(tree: PhaseNode[]): PhaseNode[] {
  const t = cloneTree(tree)
  const filled = new Map<string, boolean>()
  walk(t, (n) => {
    filled.set(n.key, n.deliverables.some((d) => !d.planned))
  })
  const leaves = flattenTree(t).filter((x) => x.node.folders.length === 0)
  const currentKey = leaves.find((x) => !filled.get(x.node.key))?.node.key ?? null

  const compute = (n: PhaseNode): PhaseState => {
    if (n.folders.length > 0) {
      const childStates = n.folders.map(compute)
      n.state = childStates.every((s) => s === 'done') ? 'done' : 'doing'
    } else {
      n.state = filled.get(n.key) ? 'done' : n.key === currentKey ? 'doing' : 'todo'
    }
    return n.state
  }
  t.forEach(compute)
  return t
}

export interface TreeStats {
  total: number
  done: number
  docs: number
}

export function treeStats(tree: PhaseNode[]): TreeStats {
  const all = flattenTree(tree)
  return {
    total: all.length,
    done: all.filter((x) => x.node.state === 'done').length,
    docs: all.reduce((s, x) => s + x.node.deliverables.filter((d) => !d.planned).length, 0),
  }
}


/* ---------------- 状态文案 ---------------- */

const PHASE_STATE_LABEL: Record<PhaseState, string> = { done: '已完成', doing: '进行中', todo: '未开始' }
const DELIVERABLE_STATE_LABEL: Record<DeliverableState, string> = { ok: '定稿', doing: '撰写中', todo: '待开始' }

export function phaseStateLabel(s: PhaseState | undefined): string {
  return s ? PHASE_STATE_LABEL[s] : '未开始'
}

export function deliverableStateLabel(d: PhaseDeliverable): string {
  return d.planned ? '待起草' : DELIVERABLE_STATE_LABEL[d.state]
}

/**
 * 阶段行右侧元信息。三种情况严格分开，避免「2 个子阶段 · 」这种尾巴挂分隔符
 * （拼接时没判空留下的，截图里一眼能看到）。
 */
export function phaseMetaText(childCount: number, fileCount: number): string {
  if (childCount && fileCount) return `${childCount} 个子阶段 · ${fileCount} 个文件`
  if (childCount) return `${childCount} 个子阶段`
  if (fileCount) return `${fileCount} 个文件`
  return '空'
}
