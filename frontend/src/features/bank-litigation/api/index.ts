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

/** 案件列表（双层 cases） */
export async function listCases(): Promise<components['schemas']['CaseOut'][]> {
  return casesApi.get('cases').json<components['schemas']['CaseOut'][]>()
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
  const res = await docConvertApi.post('convert', {
    // ⚠️ ky 的 FormData 走 `body:`，不是 `json:` —— 写成 json 会让 ky
    // 去序列化 FormData（结果是空 body 或直接抛错），请求发不出去，
    // 界面永远停在「转换中…」。参考 material-prep 的 uploadPack 写法。
    body: form,
    // 转换要过一遍服务端的文档解析，比普通请求慢得多；用上传档的超时。
    timeout: 120_000,
  })
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

// ───────────────────────── OA 盖章 ─────────────────────────

/**
 * 盖章申请。
 *
 * ═══ 与立案的差别（读接口才明白）═══
 * 立案是「给合同建一个 OA 项目」，入参是 contract_id；
 * 而盖章/归档的入参是 **file_path** —— 它按文件所在目录反查文件夹绑定，
 * 再由绑定找到合同。所以这两个动作的前提不是「有合同」，而是
 * 「这份文件在已绑定的本地文件夹里」。
 *
 * ⚠️ 反查失败时后端回 404「无法根据文件路径找到关联合同」，
 * 而权限不足也回同一个 404（防探测他人合同）。前端不做猜测，原样展示。
 */
export const oaStampApi = createApiClient({ prefix: '/api/v1/oa-stamp' })

export type StampApplyIn = components['schemas']['StampApplyIn']
export type StampLookupOut = components['schemas']['StampLookupOut']
export type StampSessionOut = components['schemas']['StampSessionOut']

/** 按文件路径反查合同（盖章前置：先确认系统认得出这份文件属于哪件） */
export async function lookupStampContract(payload: StampApplyIn): Promise<StampLookupOut> {
  return oaStampApi.post('lookup', { json: payload }).json<StampLookupOut>()
}

/** 提交盖章申请（后台线程驱动 OA） */
export async function applyStamp(payload: StampApplyIn): Promise<StampSessionOut> {
  return oaStampApi.post('apply', { json: payload }).json<StampSessionOut>()
}

/** 轮询盖章会话 */
export async function getStampSession(sessionId: number): Promise<StampSessionOut> {
  return oaStampApi.get(`session/${sessionId}`).json<StampSessionOut>()
}

// ───────────────────────── OA 归档 ─────────────────────────

export const oaArchiveApi = createApiClient({ prefix: '/api/v1/oa-archive' })

export type ArchiveApplyIn = components['schemas']['ArchiveApplyIn']
export type ArchiveLookupOut = components['schemas']['ArchiveLookupOut']
export type ArchiveSessionOut = components['schemas']['ArchiveSessionOut']
export type OpenOAIn = components['schemas']['OpenOAIn']
export type OpenStampIn = components['schemas']['OpenStampIn']

/** 按文件路径反查合同（归档前置） */
export async function lookupArchiveContract(payload: ArchiveApplyIn): Promise<ArchiveLookupOut> {
  return oaArchiveApi.post('lookup', { json: payload }).json<ArchiveLookupOut>()
}

/** 提交归档（可一次传多个文件路径） */
export async function applyArchive(payload: ArchiveApplyIn): Promise<ArchiveSessionOut> {
  return oaArchiveApi.post('apply', { json: payload }).json<ArchiveSessionOut>()
}

/** 轮询归档会话 */
export async function getArchiveSession(sessionId: number): Promise<ArchiveSessionOut> {
  return oaArchiveApi.get(`session/${sessionId}`).json<ArchiveSessionOut>()
}

/**
 * 在 OA 里打开该合同（把用户带到 OA 页面，不跑自动化）。
 * 用于「代码跑完，人去看一眼」的场景。
 */
export async function openContractInOA(payload: OpenOAIn): Promise<{ success: boolean; message: string }> {
  return oaArchiveApi.post('open-oa', { json: payload }).json<{ success: boolean; message: string }>()
}
