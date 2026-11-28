/**
 * `ui_action` / `ui_snapshot_request` 帧 → store / 页面注册表。
 *
 * ## 为什么界面动作不走 `applyToolCall`（工具行 + 转录）
 *
 * 界面动作不是「工具调用记录」，结果已经落在页面上，写进转录既回放不出来也无法撤销
 * （见 store/ui-tools.ts 文件头）。
 *
 * ## 为什么返回的键名是 `onUiAction` 而不是 `ui_action`
 *
 * 这里最初照施工图写成「键 = 事件类型名」，结果**整条链路是死的**：`StreamHandlers`
 * 的成员是回调名（`onXxx`），而事件分发是 `streaming.ts` 里一棵写死的
 * `switch (event.type)`。键名写成 `ui_action` 既不会被分发器查到，也**不会编译报错**
 * ——`turn-handlers.ts` 用展开合并，TS 的 excess-property 检查对 spread 不生效
 * （2026-11-27 红队评审 P0-1）。所以这里返回 `Pick<StreamHandlers, 'onUiAction'>`，
 * 让「分发器少一个 case」在类型层面就有依赖关系，另配 `streaming.ui-action.test.ts`
 * 钉死真实分发路径。`ui_snapshot_request` 照同一副药：`Pick` 管类型、
 * `streaming.ui-snapshot.test.ts` 管分发。
 *
 * ## 为什么在**工厂里**清打断标记
 *
 * 本轮 handlers 每次开流都会重建（`createTurnHandlers` 在 `store/turn-send.ts` 里按轮
 * 调用），这是唯一能可靠界定「同一个 run」的时机。不清的后果是「停下」一旦点过，之后
 * 每一轮的 AI 操作都静默失效——律师只看到 AI 说「我帮你打开」，页面却永远不动。
 */

import type { StreamHandlers } from '../streaming'

import { submitUiPageSnapshot } from '../api'
import type { UiPageSnapshotReply } from '../api'
import { currentRoute, readPageState } from '../ui-tools'
import type { TurnHandlerContext } from './context'

/** 页面没声明状态时回给后端的那句话（后端据此回 `no_page_state`，见 services/ui_action/snapshot.py）。 */
const NO_PAGE_STATE_NOTE = '页面没有声明状态'

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

/**
 * `ui_snapshot_request`：读页面注册表里的结构化状态，POST 回后端那一跳的等待方。
 *
 * **不 await**（与 `onUiAction` 同一条原则）：SSE 读循环不能被一次网络往返卡住。代价是
 * 失败只能 warn——后端 3 秒后按「没问到」继续，模型据此改问律师；这比让整条流停在一次
 * 快照上便宜得多。
 *
 * **读不到时必须带 note**：只回 `state: {}` 而不解释，模型会把「页面没声明」当成「页面上
 * 什么都没有」，那是编造事实。后端把 note 转成 `no_page_state` 交给模型。
 *
 * **`available_actions` 恒发（含空数组）**：它是给模型「这一刻还能做什么」的补充。页面没声明
 * 状态时**不许**按当前地址编一份猜的动作表——模型会照着它去调一个页面根本没实现的动作，
 * 表现与 `unknown_action` 一样，却连告警都没有。
 *
 * **`blocked_actions` 同一条口径**：页面登记过的「有、但此刻做不了」原样带上（空表也要发）。
 * 少了它，模型分不清「页面没实现」与「有但此刻不可用」，会自己编一个 `packId` 去硬调。
 *
 * **`private_state` 是另一半，同一条应答带上、但去向相反**：后端只记日志，永不放进
 * `ui_page_state` 的返回值。两半在这里汇合是刻意的（一次上行只发一份），分开就变成两条
 * 需要各自对齐的通道；而把 `read.privateState` 错填到 `state` 里就等于把草稿交给模型当
 * 既成事实——`streaming.ui-snapshot.test.ts` 钉死了这件事不发生。
 */
export function createUiSnapshotHandler(): Pick<StreamHandlers, 'onUiSnapshotRequest'> {
  return {
    onUiSnapshotRequest: (event) => {
      const read = readPageState(event.page ?? undefined)
      const reply: UiPageSnapshotReply = read
        ? {
            state: read.state,
            route: read.route,
            available_actions: read.availableActions,
            blocked_actions: read.blockedActions,
            private_state: read.privateState,
          }
        : {
            state: {},
            route: currentRoute(),
            note: NO_PAGE_STATE_NOTE,
            available_actions: [],
            blocked_actions: [],
            // 页面都没声明：私有那一半同样只能发空对象（不许按当前地址编一份猜的）
            private_state: {},
          }
      void submitUiPageSnapshot(event.request_id, reply).catch((error: unknown) => {
        console.warn(`[ui-snapshot] 快照应答未送达（request_id=${event.request_id}）：${String(error)}`)
      })
    },
  }
}
