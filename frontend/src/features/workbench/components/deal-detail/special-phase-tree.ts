/**
 * 专项阶段树（最多 3 级）——**统一出口**。
 *
 * 原来是单文件（367 行、20+ 个导出），同时承担构造/规范化、只读遍历、结构操作、
 * 目录名派生四件事：读代码要逐函数判断「它会不会动我的树」。现在按副作用边界
 * 拆成三件纯函数模块，本文件只做 re-export，**调用方的 import 路径一行不用改**：
 *
 * - `phase-tree.ts`：类型（`PhaseNode` / `PhaseDeliverable` / `PhaseState`）、
 *   `MAX_DEPTH`、`newPhaseKey` / `blankPhase` / `normalizeTree` / `cloneTree`；
 * - `phase-tree-query.ts`：只读遍历（`walk` / `flattenTree` / `findByKey` /
 *   `parentOf`）与编号推导；
 * - `phase-tree-ops.ts`：结构操作（移动 / 增删 / 升降级 / 改名 / 展开态），
 *   一律「先 clone 再改」，返回新树。
 *
 * 目录名派生（`folderNameOf`）随「阶段行文案/元信息」归 `special-phase-state.ts`。
 * 同域兄弟模块：状态推导 `special-phase-state.ts`，交付物增删 `special-phase-crud.ts`。
 */

export * from './phase-tree'
export * from './phase-tree-query'
export * from './phase-tree-ops'
export { folderNameOf } from './special-phase-state'
