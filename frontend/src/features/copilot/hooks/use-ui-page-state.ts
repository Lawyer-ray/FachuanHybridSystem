/**
 * 页面声明「AI 可以读的那部分状态」—— 一行接入。
 *
 * ## 用法（材料预处理页）
 *
 * ```tsx
 * export function MaterialPrepPage() {
 *   const location = useLocation()
 *   const [stage, setStage] = useState<MaterialPrepStage>('todo')
 *   const [selected, setSelected] = useState<string | null>(null)
 *   // 只声明判断下一步真正要用的字段：整页状态进模型上下文既贵又容易过期
 *   useUiPageState(
 *     'material-prep',
 *     {
 *       page: 'material-prep',
 *       route: location.pathname + location.search,
 *       stage,
 *       selected,
 *     },
 *     // 「有、但此刻做不了」：没选中包时 judge 调不出正确结果（模型会自己编一个 packId）
 *     {
 *       blockedActions:
 *         selected === null
 *           ? [{ name: 'ui_material_prep_judge', reason: '当前没有选中材料包：先让律师选一条' }]
 *           : [],
 *       // 不进模型上下文的那一半：未提交草稿 / 原始 id / 调试字段（这里放的是原始地址）
 *       privateState: { openDetail: location.pathname },
 *     },
 *   )
 *   // ...页面其余部分
 * }
 * ```
 *
 * ## 为什么 provider 从 ref 读值，而不是把 state 放进 effect 依赖
 *
 * `state` 每次渲染都是新对象：放进依赖就会每帧重注册一遍（注册表要维护注册顺序、dev 探针
 * 也会收到一串无意义的读）。真正需要跟渲染更新的只有「读到什么」，所以注册 effect 只依赖
 * `page`，注册关系在整个挂载期稳定。
 */

import { useEffect, useRef } from 'react'

// 直连实现文件，**不要**改成 `from '../ui-tools'`（桶）：桶会引 `registry.ts` → `discover.ts`，
// 而 discover 是 `import.meta.glob('/src/features/<feature>/ui-actions.ts', { eager: true })`。
// 页面引本 hook 的那一刻就会把 registry + 整张 eager glob 表拉进自己的 chunk，还从 discover
// 回转到本 feature——「页面 → copilot/ui-tools → discover → 本 feature」的回头路。
// 页面侧的统一入口是 `ui-tools/contract.ts`（它只转出这些轻符号）。
import {
  clearPageBlockedActions,
  clearPagePrivateState,
  registerPageState,
  setPageBlockedActions,
  setPagePrivateState,
  unregisterPageState,
} from '../ui-tools/page-state'
import type { BlockedAction } from '../ui-tools/page-state'

export function useUiPageState(
  page: string,
  state: Record<string, unknown>,
  options?: {
    blockedActions?: BlockedAction[]
    /** 不进模型上下文的那一半（未提交草稿 / 原始 id / 调试字段）；缺省 = 空对象 */
    privateState?: Record<string, unknown>
  },
): void {
  const latest = useRef(state)
  // 先同步最新值（同一 commit 内 effects 按声明序执行）：首帧就被问也能读到真值。
  useEffect(() => {
    latest.current = state
    // 「做不了什么」**每次渲染都写一遍**：它随选择变化（律师选了一条就不再 blocked），
    // 只在挂载时写一次会让模型一直读到挂载那一刻的旧原因——那是本字段最坏的失效形态
    // （页面明明能做了，AI 却还在说「先选一条」）。写一个 Map 很便宜，漏更新不是。
    //
    // 这一份也不像 `state` 那样需要 ref：`state` 留的是**稍后才被读**的 getter，而这里
    // 本帧读本帧写，直接推给模块表就已经是最新值。
    setPageBlockedActions(page, options?.blockedActions ?? [])
    // 私有那一半同一条理由：随渲染更新（草稿在变），只在挂载时写一次就永远是旧草稿。
    // 它不进模型上下文，所以频繁写的坏处只是多一次 Map 赋值；不写的坏处是日志里一份过期快照。
    setPagePrivateState(page, options?.privateState ?? {})
  })
  useEffect(() => {
    const provider = (): Record<string, unknown> => latest.current
    registerPageState(page, provider)
    return () => unregisterPageState(page, provider)
  }, [page])
  // 卸载 / 换页即撤：页面没了还回旧原因，等于让模型对着不存在的页面下结论。
  // 私有那一半同理：上一个实例的草稿属于上一个实例，挂在表里就是假事实。
  useEffect(
    () => () => {
      clearPageBlockedActions(page)
      clearPagePrivateState(page)
    },
    [page],
  )
}
