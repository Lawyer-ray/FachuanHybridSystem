import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

// ───────────────────────── 案件 ─────────────────────────

export const casesApi = createApiClient({ prefix: '/api/v1/cases' })

/**
 * ⚠️⚠️ 案件接口的路径**层级不统一**，这三个实测结果必须记住
 * （client 前缀是 /api/v1/cases，下面写的是拼在前缀后的部分）：
 *
 *   'cases'                → /api/v1/cases/cases            200  列表
 *   `cases/${id}`          → /api/v1/cases/cases/406        200  详情
 *   `${id}/readiness`      → /api/v1/cases/406/readiness    200  子资源
 *   `cases/${id}/readiness`→ /api/v1/cases/cases/406/...    404  ✗ 错法
 *
 * 也就是说：**列表和详情是双层，子资源是单层**。
 * 踩过一次：子资源也写成 `cases/${id}/...` → 404，而前端表现是
 * 「起诉条件校验失败」，看着像业务错误，实际只是 URL 拼错。
 */

/**
 * 案件列表（双层 cases）。
 *
 * 带 `slim=true`：本页是后端列表接口**唯一的重消费方**，但只读 7 个标量字段
 * （见 `types.ts` 的 `CaseRow`），而全量 `CaseOut` 每行还背着 7 个嵌套集合——
 * 真库 115 行实测 258 条 SQL / 755 KB。slim 走 `CaseSlimOut`（标量列与 CaseOut
 * 同口径），后端同步裁掉预取。
 * 分页暂不动：后端已支持 `limit/offset` + `with_total=true`（总数在 `X-Total-Count`
 * 响应头），但本页还没有分页 UI；现在默认 200 条上限够用，加 UI 是独立的交互改动。
 */
export async function listCases(): Promise<components['schemas']['CaseSlimOut'][]> {
  return casesApi
    .get('cases', { searchParams: { slim: 'true' } })
    .json<components['schemas']['CaseSlimOut'][]>()
}

/** 单个案件详情（双层 cases） */
export async function getCase(caseId: number): Promise<components['schemas']['CaseOut']> {
  return casesApi.get(`cases/${caseId}`).json<components['schemas']['CaseOut']>()
}

/** 材料齐备度：回答「这件能不能递立案」 */
export type MaterialStatus =
  components['schemas']['MaterialStatusOut']

export async function getMaterialStatus(caseId: number): Promise<MaterialStatus> {
  return casesApi.get(`${caseId}/material-status`).json<MaterialStatus>()
}

/** 起诉条件 / 答辩条件（按 current_stage 后端自动分流） */
export type Readiness = components['schemas']['CaseReadinessOut']

export async function getReadiness(caseId: number): Promise<Readiness> {
  return casesApi.get(`${caseId}/readiness`).json<Readiness>()
}

/** 利益冲突预检（red 阻断 / yellow 复核 / neutral 提示） */
export type ConflictCheck = components['schemas']['ConflictCheckOut']

export async function runConflictCheck(caseId: number): Promise<ConflictCheck> {
  return casesApi.post(`${caseId}/conflict-check`).json<ConflictCheck>()
}
