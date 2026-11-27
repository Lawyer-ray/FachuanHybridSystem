/**
 * 页面状态快照的回传（AI 问「现在页面上是什么」的那一跳）。
 *
 * 从 `api.ts` 拆出：它与 UI 动作回执同属「上行应答」这一族（都不是会话 CRUD），
 * 而 `api.ts` 已到软红线。`api.ts` 仍 re-export 这里的符号，import 路径不变。
 */

import { api } from '@/lib/api'

/** 请求体（`POST /agent/ui-snapshots/{request_id}` 的冻结契约，镜像后端 `UiSnapshotIn`）。 */
export interface UiPageSnapshotReply {
  state: Record<string, unknown>
  /** 读出那一刻的地址：模型据此知道「看到的是哪一页」。 */
  route: string
  /** 页面没有声明状态时带这句：后端据此回 `no_page_state`，不许把空对象当成空页面。 */
  note?: string
  /**
   * 这个地址上模型还能调的动作名（`ui-tools/page-state.ts` 的 `availableActionsForPath`）。
   *
   * 字段名逐字 `available_actions`（后端契约同一拼法），上限 10、两端各截一次。只放名字不放
   * 参数结构，所以截断是安全的——少一条可选项，不是「这个字段不存在」。
   * 页面没声明状态时传空数组：那一刻的状态表里没有被登记的页面，动作清单只能是猜的。
   */
  available_actions: string[]
}

/** 快照应答的回执。`success=false` 不是失败：等待方（≤3s）可能已经超时。 */
export interface UiPageSnapshotReceipt {
  accepted: boolean
  success: boolean
  /** 拒绝理由（鉴权失败 / 状态超量）：只在 `accepted=false` 时有。 */
  error?: string
}

/**
 * 回传一次页面状态快照（与动作回执同域同鉴权）。
 *
 * **有时限**：后端只等 3 秒，晚到的应答会被记下但模型已按「没问到」继续；所以调用方
 * 不 await（见 `handlers/ui-action-handler.ts` 的接线）。
 */
export function submitUiPageSnapshot(
  requestId: string,
  payload: UiPageSnapshotReply,
): Promise<UiPageSnapshotReceipt> {
  return api.post(`agent/ui-snapshots/${requestId}`, { json: payload }).json<UiPageSnapshotReceipt>()
}
