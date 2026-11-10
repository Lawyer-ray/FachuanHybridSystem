import { createApiClient } from '@/lib/api'
import type { InvoiceActionResult, InvoiceIntake, SelectableContract } from './types'

/**
 * 发票待认领 API 客户端。
 *
 * ⚠️ 前缀必须写**完整的绝对路径** `/api/v1/...`。
 *
 * `createApiClient` 内部是 `{ prefix: API_BASE_URL, ...options }`——传入的
 * options 在默认值**之后**展开，所以这里给的 prefix 会**整体覆盖** `/api/v1`，
 * 而不是接在它后面。只写 `/contracts/finance/invoice-intake` 会请求到
 * `http://host/contracts/finance/invoice-intake/...`（缺 /api/v1）→ 404，
 * 表现是首页卡片一直加载不出来，而 tsc/lint 全绿（款项侧踩过这个坑，
 * 见 payment-intake/api.test.ts 的锁死断言）。
 *
 * ## ⚠️ 本前缀**未定稿**
 *
 * 与款项待认领（已实测 `/api/v1/contracts/finance/intake`）同构地写成
 * `/api/v1/contracts/finance/invoice-intake`，但后端 P5 尚未装配该 router。
 * **待 P5 后端定稿后校对**：以 `backend/apps/contracts/api/__init__.py` 里
 * `router.add_router(...)` 的挂载前缀为准，并用
 * `curl /api/v1/openapi.json` 探活（401/403 = 路径存在仅缺鉴权；404 = 路径错）。
 * 校对时同步更新 api.test.ts 的锁死断言。
 */
export const invoiceIntakeApi = createApiClient({ prefix: '/api/v1/contracts/finance/invoice-intake' })

/** 待认领列表 query key（首页模块订阅；确认/驳回后 invalidate） */
export const INVOICE_INTAKE_PENDING_KEY = ['invoice-intake-pending'] as const
export const INVOICE_INTAKE_COUNT_KEY = ['invoice-intake-count'] as const

/** 下拉搜索的 query key */
export const INVOICE_SELECTABLE_KEY = ['invoice-intake-selectable'] as const

/** GET /pending —— 与我相关的待确认发票（后端按收件人/主办律师/管理员收敛） */
export async function listPendingInvoices(limit = 20): Promise<InvoiceIntake[]> {
  return invoiceIntakeApi.get('pending', { searchParams: { limit: String(limit) } }).json<InvoiceIntake[]>()
}

/** GET /pending/count —— 首页角标（轻量） */
export async function getPendingInvoiceCount(): Promise<number> {
  const res = await invoiceIntakeApi.get('pending/count').json<{ count: number }>()
  return res.count
}

/** GET /{id} —— 详情（完整候选 + 被排除线索 + 收款候选） */
export async function getInvoiceIntake(id: number): Promise<InvoiceIntake> {
  return invoiceIntakeApi.get(String(id)).json<InvoiceIntake>()
}

/** GET /selectable-contracts —— 「换个项目」下拉（与自动匹配共用资格规则） */
export async function listSelectableContracts(search = '', limit = 50): Promise<SelectableContract[]> {
  return invoiceIntakeApi
    .get('selectable-contracts', { searchParams: { search, limit: String(limit) } })
    .json<SelectableContract[]>()
}

/**
 * POST /{id}/confirm —— 确认绑定并生成发票记录。
 *
 * `contractId` / `paymentId` 省略 = 采纳系统建议；传入即人工改判。
 */
export async function confirmInvoiceIntake(
  id: number,
  contractId?: number,
  paymentId?: number,
): Promise<InvoiceActionResult> {
  return invoiceIntakeApi
    .post(`${id}/confirm`, {
      json: { contract_id: contractId ?? null, payment_id: paymentId ?? null },
    })
    .json<InvoiceActionResult>()
}

/** POST /{id}/reject —— 标记为无关发票（不是本所项目该收的票） */
export async function rejectInvoiceIntake(id: number, reason: string): Promise<InvoiceActionResult> {
  return invoiceIntakeApi.post(`${id}/reject`, { json: { reason } }).json<InvoiceActionResult>()
}

/** POST /{id}/reopen —— 撤销裁定回到待确认（会同时清理已生成的发票记录） */
export async function reopenInvoiceIntake(id: number): Promise<InvoiceActionResult> {
  return invoiceIntakeApi.post(`${id}/reopen`).json<InvoiceActionResult>()
}

/** POST /rescan —— 手动补扫近 N 天邮件 */
export async function rescanInvoiceIntakes(
  days = 14,
): Promise<{ scanned: number; created: number; skipped: number; days: number }> {
  return invoiceIntakeApi
    .post('rescan', { searchParams: { days: String(days) } })
    .json<{ scanned: number; created: number; skipped: number; days: number }>()
}
