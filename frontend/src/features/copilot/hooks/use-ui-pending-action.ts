/**
 * 页面挂载时取走「排队等这一页」的动作，交给页面自己的 handler 执行。
 *
 * 典型链路：模型说「打开材料预处理的待处理并展开筛选」→ 动作落在尚未挂载的页面上
 * → `runUiTool` 把请求排进 `ui-tools/pending.ts` 再 `navigate` → 页面挂载，本 hook
 * 第一帧就把请求取走并交给 handler。**取出即清**（`takePageActions`），所以页面重挂载
 * 不会把同一个请求再执行一次。
 *
 * `page` 必须与后端清单里该动作的 `route` **字面量一致**（`spec.route` 就是这个键）：
 * 两边拼写不同时页面永远取不到，表现为「跳过去了但什么都没发生」——这是本机制唯一
 * 的静默失败点，所以约定里要求页面写 `useUiPendingAction(ROUTES.xxx, handle)`，
 * 而 manifest 侧同样用 `ROUTES.xxx` 的值。
 *
 * `handle` 不稳定（内联箭头）时本 effect 每次渲染重跑，但那一次取到的是空队列
 * （上一次已经清空），不会重复执行；仍建议用 `useCallback` 固定，省掉无谓的取队。
 */

import { useEffect } from 'react'

// 直连实现文件，**不要**改成 `from '../ui-tools'`（桶）：桶 → `registry.ts` → `discover.ts`，
// 而 discover 是 `import.meta.glob('/src/features/<feature>/ui-actions.ts', { eager: true })`。
// 页面引本 hook 的那一刻就会把 registry + 整张 eager glob 表拉进自己的 chunk，还从 discover
// 回转到本 feature——「页面 → copilot/ui-tools → discover → 本 feature」的回头路。
// 页面侧的统一入口是 `ui-tools/contract.ts`（它只转出这些轻符号）。
import { takePageActions } from '../ui-tools/pending'
import type { UiActionRequest } from '../ui-tools/types'

export function useUiPendingAction(page: string, handle: (request: UiActionRequest) => void): void {
  useEffect(() => {
    for (const request of takePageActions(page)) handle(request)
  }, [page, handle])
}
