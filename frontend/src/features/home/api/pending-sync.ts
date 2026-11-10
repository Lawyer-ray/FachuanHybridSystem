import { createApiClient } from '@/lib/api'

/**
 * 首页「待认领」卡同步按钮（/api/v1/contracts/finance/intake/sync-pending）。
 *
 * 挂在前缀 `/api/v1/contracts/finance/intake` 下的**款项**路由里，但收的是
 * **两类**（到账款项 + 发票）——服务端一次编排，前端只调一次。让浏览器分别调
 * 两个 rescan 端点，就得在 UI 层拼两套加载态与错误态，那是把服务端职责漏到前端。
 *
 * ⚠️ 前缀写完整绝对路径：`createApiClient` 的 options 在默认值之后展开，
 * 这里给的 prefix 会**整体覆盖** `/api/v1`，只写相对段会 404（款项侧踩过）。
 */
export const pendingSyncApi = createApiClient({ prefix: '/api/v1/contracts/finance/intake' })

/** POST /sync-pending 的响应：两类各收进多少条 + 提交了几个 IMAP 异步任务 */
export interface PendingSyncResult {
  days: number
  payment_created: number
  invoice_created: number
  /** 已提交的 IMAP 来源数。>0 表示还有新邮件在后台拉，几秒后可能再出现新条目 */
  sources_submitted: number
}

/**
 * 补扫最近 `days` 天的邮件，把未处理过的到账与发票收进待认领。
 *
 * 服务端先补扫**已入库**邮件（同步、秒级），再提交 IMAP 异步同步拉新邮件。
 * 因此调用方拿到结果后仍该在随后几秒重取列表——后台拉回来的那批会晚一步到。
 */
export async function syncPendingIntakes(days = 1): Promise<PendingSyncResult> {
  return pendingSyncApi
    .post('sync-pending', { searchParams: { days: String(days) } })
    .json<PendingSyncResult>()
}
