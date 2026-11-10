import { createApiClient } from '@/lib/api'
import type { Intake, IntakeActionResult, SelectableContract } from './types'

/**
 * 到账待认领 API 客户端。
 *
 * ⚠️ 前缀**不是** `/api/v1/finance/intake`：后端路由在
 * `contracts/api/__init__.py` 里以 `/finance/intake` 挂在 contracts 路由下，
 * 最终路径是 `/api/v1/contracts/finance/intake/*`。
 * 已用 `curl /api/v1/openapi.json` 核对过（禁止凭印象拼路径）。
 */
export const intakeApi = createApiClient({ prefix: '/contracts/finance/intake' })

/** 待认领列表 query key（首页模块订阅；确认/撤销后 invalidate） */
export const INTAKE_PENDING_KEY = ['payment-intake-pending'] as const
export const INTAKE_COUNT_KEY = ['payment-intake-count'] as const

/** 下拉搜索的 query key */
export const INTAKE_SELECTABLE_KEY = ['payment-intake-selectable'] as const

/** GET /pending —— 与我相关的待确认到账（后端已按收件人/主办律师/管理员收敛） */
export async function listPendingIntakes(limit = 20): Promise<Intake[]> {
  return intakeApi.get('pending', { searchParams: { limit: String(limit) } }).json<Intake[]>()
}

/** GET /pending/count —— 首页角标（轻量） */
export async function getPendingCount(): Promise<number> {
  const res = await intakeApi.get('pending/count').json<{ count: number }>()
  return res.count
}

/** GET /{id} —— 详情（完整候选 + 被排除线索） */
export async function getIntake(id: number): Promise<Intake> {
  return intakeApi.get(String(id)).json<Intake>()
}

/** GET /selectable-contracts —— 「换个项目」下拉（与自动匹配共用资格规则） */
export async function listSelectableContracts(search = '', limit = 50): Promise<SelectableContract[]> {
  return intakeApi
    .get('selectable-contracts', { searchParams: { search, limit: String(limit) } })
    .json<SelectableContract[]>()
}

/** POST /{id}/confirm —— 确认归属并写入收款记录。contractId 省略 = 采纳系统建议 */
export async function confirmIntake(id: number, contractId?: number, note = ''): Promise<IntakeActionResult> {
  return intakeApi
    .post(`${id}/confirm`, { json: { contract_id: contractId ?? null, note } })
    .json<IntakeActionResult>()
}

/** POST /{id}/reject —— 标记为非记账事件 */
export async function rejectIntake(id: number, reason: string): Promise<IntakeActionResult> {
  return intakeApi.post(`${id}/reject`, { json: { reason } }).json<IntakeActionResult>()
}

/** POST /{id}/ignore —— 标记为不需记账（往来款/退款） */
export async function ignoreIntake(id: number, reason: string): Promise<IntakeActionResult> {
  return intakeApi.post(`${id}/ignore`, { json: { reason } }).json<IntakeActionResult>()
}

/** POST /{id}/reopen —— 撤销裁定回到待确认（会同时删除已生成的收款记录） */
export async function reopenIntake(id: number): Promise<IntakeActionResult> {
  return intakeApi.post(`${id}/reopen`).json<IntakeActionResult>()
}

/** POST /rescan —— 手动补扫近 N 天邮件 */
export async function rescanIntakes(days = 14): Promise<{ scanned: number; created: number; skipped: number; days: number }> {
  return intakeApi
    .post('rescan', { searchParams: { days: String(days) } })
    .json<{ scanned: number; created: number; skipped: number; days: number }>()
}
