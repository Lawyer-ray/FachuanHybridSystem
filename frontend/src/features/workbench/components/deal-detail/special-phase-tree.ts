/**
 * 专项阶段树（最多 3 级）——不可变操作的纯函数模块（54 号原型 phase-tree.js 的直译）。
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
 * 所有结构操作返回新树（不改入参），渲染只负责画。兄弟模块：状态推导与文案在
 * `special-phase-state.ts`，交付物增删在 `special-phase-crud.ts`。
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

/**
 * 任意形状 → 规范树。
 *
 * 容错后端/本地缓存给的松散数据（缺字段、children 里超过 3 级），并**把超过
 * MAX_DEPTH 的层级拍平丢弃**——与其渲染出一个页面表达不了的 4 级，不如在
 * 数据入口就收敛。
 */
/** 规范化入参：容忍后端/本地缓存给的松散 JSON（缺字段、多嵌套） */
export interface LoosePhaseNode extends Partial<Omit<PhaseNode, 'folders'>> {
  folders?: LoosePhaseNode[]
}

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

/* ---------------- 遍历 ---------------- */

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
function last(path: number[]): number {
  return path[path.length - 1] ?? 0
}

/** 节点的存放容器（根层就是 tree 本身，否则是父节点的 folders） */
function siblingsOf(tree: PhaseNode[], key: string): PhaseNode[] {
  const par = parentOf(tree, key)
  return par ? par.node.folders : tree
}

/* ---------------- 结构操作（全部返回新树） ---------------- */

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

/* ---------------- 阶段 = 文件夹（目录名派生） ---------------- */

/**
 * 目录名 = `<编号>-<阶段名>`（如 `3.1-职工安置文书`）。
 *
 * 阶段即文件夹：律师在系统里看到的树与磁盘上交付给客户的结构逐字一致。
 * 右栏「合同文件夹」必须**由阶段树派生**，不能另存一份——原型里独立写死的
 * 目录名在阶段改名后立刻与左栏对不上。
 */
export function folderNameOf(item: FlatPhase): string {
  return `${item.no}-${item.node.name}`
}
