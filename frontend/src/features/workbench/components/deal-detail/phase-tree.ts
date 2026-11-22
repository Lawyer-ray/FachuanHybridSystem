/**
 * 专项阶段树（最多 3 级）——**类型 + 构造/规范化**（54 号原型 phase-tree.js 的直译）。
 *
 * **为什么是树而不是扁平数组**：阶段名可改、层级可递进（1-2-3 级）、顺序可调。
 * 扁平数组表达不了层级；嵌套对象就地改又会在跨层搬节点时留下悬挂引用
 * （「父节点引用还在、子节点已经不在树里」）。
 *
 * **为什么主键是 key 而不是 name**：改名不得丢掉交付物。原型早期用名字匹配
 * 交付物，换模板再换回来时丢过一次数据（见原型 README 第十节）——那是后端
 * 必须用稳定 key 的原型级证据。
 *
 * **为什么编号不存数据**：`1 / 1.1 / 3.1.1` 由路径推导，存在节点上重排后立刻过期。
 *
 * 本模块只放「树长什么样 + 怎么把松散数据收敛成树」；遍历在
 * `phase-tree-query.ts`，结构操作在 `phase-tree-ops.ts`（都是纯函数，返回新树）。
 * 外部继续从 `special-phase-tree.ts` 引——那里是这三件的统一出口。
 */

/** 层级上限：三级足够表达「主线 → 子阶段 → 细项交付阶段」，再多就该拆合同 */
export const MAX_DEPTH = 3

/** 交付物状态：定稿 / 撰写中 / 待开始（计划项无文件，恒为 todo） */
export type DeliverableState = 'ok' | 'doing' | 'todo'

export interface PhaseDeliverable {
  /** 稳定 id（同阶段内唯一）：点开编辑器、删行都按它定位，不用数组下标 */
  id: string
  /** yyyy-mm-dd；计划项为空串 */
  date: string
  /** 展示名（带书名号） */
  name: string
  /** 版本号 v1/v2；计划项为空串 */
  version: string
  state: DeliverableState
  /** 已落盘的文件（相对合同文件夹根的 subpath）；计划项没有文件 */
  subpath?: string
  /** 是否有实际文件：有=已完成判定依据，无=计划中的交付物 */
  planned: boolean
}

/** 阶段状态：已完成 / 进行中 / 未开始（父节点由子节点聚合） */
export type PhaseState = 'done' | 'doing' | 'todo'

export interface PhaseNode {
  key: string
  name: string
  /** 验收标准（「到什么程度算这一步做完」）；空串 = 律师还没写 */
  acceptance: string
  /** 该阶段展开态（存节点上而不是渲染临时变量：改名重绘后不该全收起） */
  open: boolean
  /** 该阶段的开始日（用于周期轴里程碑）；无则不上轴 */
  startDate: string
  /** 子阶段（最多 MAX_DEPTH 级） */
  folders: PhaseNode[]
  deliverables: PhaseDeliverable[]
  /** 状态由 derivePhaseStates 推导，只读消费 */
  state?: PhaseState
}

/* ---------------- 构造与规范 ---------------- */

let seq = 0
/** 稳定 key 生成器（时间戳 + 自增，同一会话内不撞） */
export function newPhaseKey(prefix = 'ph'): string {
  seq += 1
  return `${prefix}_${Date.now().toString(36)}_${seq}`
}

export function newDeliverableId(): string {
  return newPhaseKey('dl')
}

/** 空白阶段（新建时用；名字留空由律师填） */
export function blankPhase(name = ''): PhaseNode {
  return {
    key: newPhaseKey(),
    name,
    acceptance: '',
    open: false,
    startDate: '',
    folders: [],
    deliverables: [],
  }
}

/** 规范化入参：容忍后端/本地缓存给的松散 JSON（缺字段、多嵌套） */
export interface LoosePhaseNode extends Partial<Omit<PhaseNode, 'folders'>> {
  folders?: LoosePhaseNode[]
}

/**
 * 任意形状 → 规范树。
 *
 * 容错后端/本地缓存给的松散数据（缺字段、children 里超过 3 级），并**把超过
 * MAX_DEPTH 的层级拍平丢弃**——与其渲染出一个页面表达不了的 4 级，不如在
 * 数据入口就收敛。
 */
export function normalizeTree(list: readonly LoosePhaseNode[] | null | undefined, depth = 1): PhaseNode[] {
  if (!list || list.length === 0) return []
  return list.map((p) => ({
    key: p.key || newPhaseKey(),
    name: p.name || '未命名阶段',
    acceptance: p.acceptance || '',
    open: !!p.open,
    startDate: p.startDate || '',
    folders: depth < MAX_DEPTH ? normalizeTree(p.folders, depth + 1) : [],
    deliverables: (p.deliverables ?? []).map((d) => ({ ...d, planned: d.planned ?? !d.subpath })),
  }))
}

/** 深拷贝（纯 JSON 数据，结构操作一律先 clone 再改，保证入参不被污染） */
export function cloneTree(tree: PhaseNode[]): PhaseNode[] {
  return tree.map((n) => ({
    ...n,
    folders: cloneTree(n.folders),
    deliverables: n.deliverables.map((d) => ({ ...d })),
  }))
}
