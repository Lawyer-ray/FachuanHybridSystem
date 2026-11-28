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

/** 列表排序口径：`filable_first` = 待立案优先（`filing_number` 为空且在办），组内 id 倒序 */
export type CaseListSort = 'filable_first'

export interface ListCasesParams {
  /** 跳过多少条（= (页码-1) × limit） */
  offset?: number
  /** 本页最多几条；默认 50，与案件列表页的 pageSize 一致 */
  limit?: number
  /** 关键词：命中 name 或 cause_of_action（后端过滤，空白串视同不传） */
  search?: string
  /** 排序口径（不传 = 后端默认顺序） */
  sort?: CaseListSort
  /** 要总数：后端回 `X-Total-Count` 响应头（已应用 search，忽略 limit/offset） */
  withTotal?: boolean
}

export interface CaseListResult {
  rows: components['schemas']['CaseSlimOut'][]
  /** 命中总数；没要总数或后端没给头时退回本页行数 */
  total: number
}

/**
 * 案件列表（双层 cases）：服务端分页 + 服务端搜索 + 服务端排序。
 *
 * 带 `slim=true`：本页是后端列表接口**唯一的重消费方**，但只读 7 个标量字段
 * （见 `types.ts` 的 `CaseRow`），而全量 `CaseOut` 每行还背着 7 个嵌套集合——
 * 真库 115 行实测 258 条 SQL / 755 KB。slim 走 `CaseSlimOut`（标量列与 CaseOut
 * 同口径），后端同步裁掉预取。
 *
 * 过滤与排序**必须下推**（本函数不提供任何前端兜底）：一页只有 50 行，
 * 前端 filter 只会筛当前页、前端 sort 只会重排当前页，翻到第 2 页就会看到
 * 与关键词无关、或「已立案」排在「待立案」前面的行。
 *   - `search`：name / cause_of_action 含关键词；
 *   - `sort=filable_first`：待立案优先（filing_number 空且在办），组内 id DESC；
 *   - `limit` + `offset`：分页；`with_total=true` 时总数走响应头，响应体仍是
 *     **裸数组**（openapi 里写过为什么不换成信封：本端点还有 workbench /
 *     material-prep / MCP 三个按裸数组消费的调用方）。
 */
export async function listCases(params: ListCasesParams = {}): Promise<CaseListResult> {
  const { offset = 0, limit = 50, search, sort, withTotal = false } = params

  const searchParams: Record<string, string> = {
    slim: 'true',
    limit: String(limit),
    offset: String(offset),
  }
  if (withTotal) searchParams.with_total = 'true'
  const keyword = search?.trim()
  if (keyword) searchParams.search = keyword
  if (sort) searchParams.sort = sort

  // 先拿 Response 再取 body：总数在响应头里，链式 .json() 会把它丢掉
  const response = await casesApi.get('cases', { searchParams })
  const rows = await response.json<components['schemas']['CaseSlimOut'][]>()
  // 头缺失（老后端 / 没要总数）或不是数字 → 退回本页行数，而不是把总数当成 0
  const header = withTotal ? response.headers.get('X-Total-Count') : null
  const parsed = header ? Number(header) : NaN
  return { rows, total: Number.isFinite(parsed) ? parsed : rows.length }
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
