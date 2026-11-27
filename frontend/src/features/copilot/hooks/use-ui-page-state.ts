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
 *   useUiPageState('material-prep', {
 *     page: 'material-prep',
 *     route: location.pathname + location.search,
 *     stage,
 *     selected,
 *   })
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
import { registerPageState, unregisterPageState } from '../ui-tools/page-state'

export function useUiPageState(page: string, state: Record<string, unknown>): void {
  const latest = useRef(state)
  // 先同步最新值（同一 commit 内 effects 按声明序执行）：首帧就被问也能读到真值。
  useEffect(() => {
    latest.current = state
  })
  useEffect(() => {
    const provider = (): Record<string, unknown> => latest.current
    registerPageState(page, provider)
    return () => unregisterPageState(page, provider)
  }, [page])
}
