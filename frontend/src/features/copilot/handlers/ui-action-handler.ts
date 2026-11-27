/**
 * `ui_action` 帧 → store 的一次 `runUiAction`。
 *
 * 为什么不走 `applyToolCall`（工具行 + 转录）：界面动作不是「工具调用记录」，结果已经
 * 落在页面上，写进转录既回放不出来也无法撤销（见 store/ui-tools.ts 文件头）。
 *
 * ## 为什么返回的键是 `onUiAction` 而不是 `ui_action`
 *
 * 这里最初照施工图写成「键 = 事件类型名」，结果**整条链路是死的**：`StreamHandlers`
 * 的成员是回调名（`onXxx`），而事件分发是 `streaming.ts` 里一棵写死的
 * `switch (event.type)`。键名写成 `ui_action` 既不会被分发器查到，也**不会编译报错**
 * ——`turn-handlers.ts` 用展开合并，TS 的 excess-property 检查对 spread 不生效
 * （2026-11-27 红队评审 P0-1）。所以这里返回 `Pick<StreamHandlers, 'onUiAction'>`，
 * 让「分发器少一个 case」在类型层面就有依赖关系，另配 `streaming.ui-action.test.ts`
 * 钉死真实分发路径。
 *
 * ## 为什么在**工厂里**清打断标记
 *
 * 本轮 handlers 每次开流都会重建（`createTurnHandlers` 在 `store/turn-send.ts` 里按轮
 * 调用），这是唯一能可靠界定「同一个 run」的时机。不清的后果是「停下」一旦点过，之后
 * 每一轮的 AI 操作都静默失效——律师只看到 AI 说「我帮你打开」，页面却永远不动。
 */

import type { StreamHandlers } from '../streaming'

import type { TurnHandlerContext } from './context'

export function createUiActionHandler(ctx: TurnHandlerContext): Pick<StreamHandlers, 'onUiAction'> {
  const { set, get } = ctx
  // 新一轮开流 = 上一轮的打断作废（理由见文件头）
  if (get().abortedAt !== null) set({ abortedAt: null })

  return {
    onUiAction: (event) => {
      // 不 await：T1 是单向指令、执行结果不回传模型（08 §3.1），卡住 SSE 读循环只会让
      // 后续帧排队。`arguments` / `route` 在契约里可选，缺省给安全默认值而不是让
      // 执行器去处理 undefined。
      void get().runUiAction({
        callId: event.call_id,
        action: event.action,
        args: event.arguments ?? {},
        route: event.route ?? null,
      })
    },
  }
}
