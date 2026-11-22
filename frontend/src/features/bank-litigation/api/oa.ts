import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

/**
 * 律所 OA 的三个动作域（立案 / 盖章 / 归档）。
 *
 * 三个域合成一个文件，是因为它们的**前提条件语义是同一套**：
 * 立案给合同建 OA 项目（入参 contract_id）；盖章与归档的入参是 **file_path**
 * ——按文件所在目录反查文件夹绑定，再由绑定找到合同。换前缀只改 client 一行。
 */

// ───────────────────────── OA 立案 ─────────────────────────

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
