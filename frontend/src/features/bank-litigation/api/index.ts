import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

/**
 * 银行批量诉讼 · 场景 2 全流程 API 层。
 *
 * ═══ 这个 feature 为什么单独存在 ═══
 * 场景 2（一份合同 → 批量出案 → 起诉 → 立案 → 归档）在后端已经**全部打通**，
 * 但前端一直没有入口：`cases` / `oa-filing` / `court-filing` / `doc-convert`
 * 这些能力只散落在各 feature 里被零碎用到，没有一个页面把这条链路串起来。
 * 本 feature 就是那条链路的唯一入口。
 *
 * ═══ 端点来源（全部已与 OpenAPI 核对）═══
 *   案件与就绪度   /api/v1/cases/*
 *   LPR 计息       /api/v1/lpr/*
 *   要素式转换     /api/v1/doc-convert/*
 *   律所 OA        /api/v1/oa-filing/*、/api/v1/oa-stamp/*、/api/v1/oa-archive/*
 *   一张网立案     /api/v1/court-filing/*
 *
 * ═══ 为什么按「域」拆成多个 client 而不是一个 ═══
 * 与 material-prep 的写法一致：每个 prefix 一个 client，路径只写后半段。
 * 好处是换前缀（比如 oa-filing 将来挪到 /oa/filing）只改一处。
 */

// ───────────────────────── 案件 ─────────────────────────

export const casesApi = createApiClient({ prefix: '/api/v1/cases' })

/**
 * 案件列表。
 *
 * ⚠️ 后端路径是 `/cases/cases`（router 前缀 `/cases` + 资源名 `cases`），
 * 不是 `/cases`。当初我在原型里按 `/cases` 调，一律 404 —— 记在这里免得再错。
 */
export async function listCases(): Promise<components['schemas']['CaseOut'][]> {
  return casesApi.get('cases').json<components['schemas']['CaseOut'][]>()
}

/** 单个案件详情 */
export async function getCase(caseId: number): Promise<components['schemas']['CaseOut']> {
  return casesApi.get(`cases/${caseId}`).json<components['schemas']['CaseOut']>()
}

/** 材料齐备度：回答「这件能不能递立案」 */
export type MaterialStatus =
  components['schemas']['MaterialStatusOut']

export async function getMaterialStatus(caseId: number): Promise<MaterialStatus> {
  return casesApi.get(`cases/${caseId}/material-status`).json<MaterialStatus>()
}

/** 起诉条件 / 答辩条件（按 current_stage 后端自动分流） */
export type Readiness = components['schemas']['CaseReadinessOut']

export async function getReadiness(caseId: number): Promise<Readiness> {
  return casesApi.get(`cases/${caseId}/readiness`).json<Readiness>()
}

/** 利益冲突预检（red 阻断 / yellow 复核 / neutral 提示） */
export type ConflictCheck = components['schemas']['ConflictCheckOut']

export async function runConflictCheck(caseId: number): Promise<ConflictCheck> {
  return casesApi.post(`cases/${caseId}/conflict-check`).json<ConflictCheck>()
}

// ───────────────────────── 要素式转换 ─────────────────────────

export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })

/** 文书类型（按类别分组） */
export type MbidList = components['schemas']['MbidListResponse']

export async function listMbidTypes(): Promise<MbidList> {
  return docConvertApi.get('mbid-list').json<MbidList>()
}

/**
 * 传统文书 → 要素式文书。
 *
 * ⚠️ 两点与普通接口不同：
 * 1. `multipart/form-data`：必须传 FormData，不能传 json；
 * 2. **响应是 docx 二进制流**，不是 JSON。所以要 `.blob()`，且文件名在
 *    Content-Disposition 里（`filename*=UTF-8''...`），需要自己解。
 *
 * 后端要求 `ZNSZJ_ENABLED=True`，未开启时返回 403。
 */
export async function convertToElemental(file: File, mbid: string): Promise<Blob> {
  const form = new FormData()
  form.append('file', file)
  form.append('mbid', mbid)
  const res = await docConvertApi.post('convert', { body: form })
  return res.blob()
}

/** 历史转换记录（最新在前，供历史弹窗浏览与重新下载） */
export type ConvertRecordList = components['schemas']['DocConvertRecordListOut']

export async function listConvertRecords(): Promise<ConvertRecordList> {
  return docConvertApi.get('records').json<ConvertRecordList>()
}

// ───────────────────────── 律所 OA ─────────────────────────

export const oaFilingApi = createApiClient({ prefix: '/api/v1/oa-filing' })

/** 当前用户可用的 OA 站点（含「有没有配凭证」） */
export type OAConfig = components['schemas']['OAConfigOut']

export async function listOAConfigs(): Promise<OAConfig[]> {
  return oaFilingApi.get('configs').json<OAConfig[]>()
}

export type ExecuteOAFilingIn = components['schemas']['ExecuteFilingIn']
/**
 * OA 立案会话。
 *
 * ⚠️ 生成物名是 `FilingSessionOut` 而不是直觉上的 `SessionOut`：
 * 本项目 social_auth 也有个 `SessionOut`（登录票据），OpenAPI 的
 * components.schemas 以类名为 key，同名只有一个能活 —— 曾被 social_auth 顶掉，
 * 导致这里拿到的是 {success,goto,state,expires_in,message} 而**没有 id**，
 * 前端永远轮询不起来。已把后端类名改成带领域前缀的 FilingSessionOut。
 */
export type OAFilingSession = components['schemas']['FilingSessionOut']

/** 触发 OA 立案（后台线程跑浏览器自动化，立即返回 session） */
export async function executeOAFiling(payload: ExecuteOAFilingIn): Promise<OAFilingSession> {
  return oaFilingApi.post('execute', { json: payload }).json<OAFilingSession>()
}

/** 轮询 OA 立案会话状态 */
export async function getOAFilingSession(sessionId: number): Promise<OAFilingSession> {
  return oaFilingApi.get(`session/${sessionId}`).json<OAFilingSession>()
}

// ───────────────────────── 一张网立案 ─────────────────────────

export const courtFilingApi = createApiClient({ prefix: '/api/v1/court-filing' })

/** 立案所需信息（含「我们是不是原告方」「有没有法院凭证」等前置判断） */
export type CaseFilingInfo = components['schemas']['CaseFilingInfoOut']

export async function getCaseFilingInfo(caseId: number): Promise<CaseFilingInfo> {
  return courtFilingApi.get(`case-info/${caseId}`).json<CaseFilingInfo>()
}

export type ExecuteCourtFilingIn = components['schemas']['ExecuteCourtFilingIn']
export type ExecuteCourtFilingOut = components['schemas']['ExecuteCourtFilingOut']

/** 执行一张网在线立案（后台线程） */
export async function executeCourtFiling(
  payload: ExecuteCourtFilingIn,
): Promise<ExecuteCourtFilingOut> {
  return courtFilingApi.post('execute', { json: payload }).json<ExecuteCourtFilingOut>()
}

/** 轮询一张网立案会话 */
export async function getCourtFilingSession(
  sessionId: number,
): Promise<ExecuteCourtFilingOut> {
  return courtFilingApi.get(`session/${sessionId}`).json<ExecuteCourtFilingOut>()
}
