import { createApiClient } from '@/lib/api'

import type { DocType, DraftAssessRequest, DraftAssessResult, DraftRequest, DraftResult } from './types'

/**
 * 文书生成 API（doc-workspace 前缀，与审查 / 版本共用同一组路由）。
 *
 * prefix 必须是**完整绝对路径**：`createApiClient({ prefix })` 里传入的 options
 * 在默认值之后展开，会整体覆盖 `/api/v1` 而不是相对拼接——只写
 * `/doc-workspace` 会打到 `http://host/doc-workspace/...` → 404，且 tsc/lint
 * 全绿（见 payment-intake/api.ts 的踩坑注释）。
 *
 * 延迟创建客户端：App 级测试会整体加载依赖图，mock 的 `@/lib/api` 未必带
 * `createApiClient`（与 doc-review-api.ts / onlyoffice/api.ts 同一处理）。
 */
let _api: ReturnType<typeof createApiClient> | null = null
function draftApi() {
  _api ??= createApiClient({ prefix: '/api/v1/doc-workspace' })
  return _api
}

/**
 * 起草超时：**远大于** ky 默认 10s。
 *
 * 一次起草是「模型逐槽写正文 → 渲染 docx → 落盘 →（可选）排一轮审查」，
 * 实测分钟级；用默认超时会把正在跑的请求当失败掐掉，前端以为失败、后端
 * 却已经把文件写进文件夹了。
 */
export const DRAFT_TIMEOUT_MS = 240_000

/**
 * 立案前判断的超时：**远大于** ky 默认 10s。
 *
 * 一次判断是一轮完整的模型比对（后端实测 20~40 秒）。用默认超时会把正在跑的判断
 * 当成失败，而失败与「材料齐全」在界面上只差一行字——律师会直接不信任这个判断。
 */
export const ASSESS_TIMEOUT_MS = 120_000

/** 文书类型清单的 query key（弹窗与测试共用同一份） */
export const DOC_TYPES_KEY = ['doc-generation', 'doc-types'] as const

/** `GET doc-types` —— 可起草的文书类型（后端只返回 is_active 的 spec）。 */
export async function listDocTypes(): Promise<DocType[]> {
  // 兼容两种出参：现约定 `{ items: [...] }`；裸数组是它之前的形状。
  // 少这个分支，下拉会静默变成「没有可用的文书类型」，比报错更难查。
  const res = await draftApi().get('doc-types').json<{ items?: DocType[] } | DocType[]>()
  return Array.isArray(res) ? res : (res.items ?? [])
}

/**
 * `POST draft-by-type` —— 按文书类型起草并落进文件夹。
 *
 * 子目录与文件名一律由后端按 `spec.folder_slot` 决定，前端不拼名字：
 * 落位规则（owner 的 FolderTemplate 里 kind 匹配的节点）只有后端知道。
 */
export async function draftByType(body: DraftRequest): Promise<DraftResult> {
  return draftApi().post('draft-by-type', { json: body, timeout: DRAFT_TIMEOUT_MS }).json<DraftResult>()
}

/**
 * `POST draft/assess` —— 材料够不够出这份文书、缺什么（只读：不渲染、不落盘）。
 *
 * 入参**没有 doc_type**：判断的是「这个案子的材料够不够」，与具体出哪份文书无关
 * （要件档案按案由命中）。弹窗里先选类型，只是为了让律师在「我要出什么」的上下文里看缺口。
 */
export async function assessDraftReadiness(body: DraftAssessRequest): Promise<DraftAssessResult> {
  return draftApi().post('draft/assess', { json: body, timeout: ASSESS_TIMEOUT_MS }).json<DraftAssessResult>()
}
