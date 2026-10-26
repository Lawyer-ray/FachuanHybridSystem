import { createApiClient } from '@/lib/api'
import type {
  ContentVersion,
  DirectEditApplyResult,
  DirectEditSuggestResult,
  ResolveAction,
  ResolveResult,
  RevisionList,
  VersionChain,
} from './types'

/**
 * 合同审查（/api/v1/contract-review）。
 *
 * 这里的复审工作台只消费「修订清单」与「决策」两组端点；
 * 上传与流水线触发仍走原有页面（材料预处理 → 发起审查）。
 */
/** 延迟创建：模块被 App 级测试整体加载时，mock 的 @/lib/api 未必提供 createApiClient */
let _reviewApi: ReturnType<typeof createApiClient> | null = null
function reviewApi() {
  _reviewApi ??= createApiClient({ prefix: '/api/v1/contract-review' })
  return _reviewApi
}

/** 取某次审查的修订清单（按 ordinal 排序，含律师已做的决策） */
export async function listRevisions(taskId: string): Promise<RevisionList> {
  return reviewApi().get(`${encodeURIComponent(taskId)}/revisions`).json<RevisionList>()
}

/**
 * 对单条修订做决策。
 *
 * - accept：标记已采纳；文档侧由编辑器以修订模式写入痕迹（前端驱动）
 * - reject：标记已驳回，不动文档；理由可留空
 * - reset：撤销决策回到待决策
 */
export async function resolveRevision(
  taskId: string,
  revisionId: string,
  action: ResolveAction,
  reason = '',
): Promise<ResolveResult> {
  return reviewApi()
    .post(`${encodeURIComponent(taskId)}/revisions/${encodeURIComponent(revisionId)}/resolve`, {
      json: { action, reason },
    })
    .json<ResolveResult>()
}

/** 审查任务状态（用于确认是否已跑完，决定能否进复审台） */
export interface ReviewTaskStatus {
  task_id: string
  status: string
  current_step?: string | null
  error_message?: string | null
  output_filename?: string | null
}

export async function getTaskStatus(taskId: string): Promise<ReviewTaskStatus> {
  return reviewApi().get(`${encodeURIComponent(taskId)}/status`).json<ReviewTaskStatus>()
}

/**
 * 取文档内容版本。
 *
 * 复审台用它决定画布该不该重建：律师逐条采纳时不应重载（采纳只改 DB
 * 状态、不写 docx）；只有编辑器保存回写后才重载成最新内容。
 */
export async function getContentVersion(taskId: string): Promise<ContentVersion> {
  return reviewApi()
    .get(`${encodeURIComponent(taskId)}/content-version`)
    .json<ContentVersion>()
}

/** 取该任务的文档版本链（客户来稿 → AI 修订版 → 律师编辑版 …） */
export async function listVersions(taskId: string): Promise<VersionChain> {
  return reviewApi()
    .get(`${encodeURIComponent(taskId)}/versions`)
    .json<VersionChain>()
}

/** 上传合同并识别当事人：返回任务 id 与识别出的四方名称 */
export interface UploadedTask {
  task_id: string
  status: string
  contract_title: string | null
  parties: Record<string, string>
}

/**
 * 上传 .docx 触发审查（识别当事人，此时流水线未启动）。
 *
 * 材料预处理里的附件要先取成 File 再上传——审查流水线只吃 docx，
 * 且需要 lxml 直接改 OOXML，走不了「引用已有附件」的捷径。
 */
export async function uploadContract(file: File, modelName = ''): Promise<UploadedTask> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  if (modelName) fd.append('model_name', modelName)
  return reviewApi().post('upload', { body: fd, timeout: 120_000 }).json<UploadedTask>()
}

/** 确认代表方 + 处理步骤，触发异步审查流水线 */
export async function confirmParty(
  taskId: string,
  payload: {
    represented_party: 'party_a' | 'party_b' | 'party_c' | 'party_d'
    reviewer_name?: string
    selected_steps?: string[]
    party_a?: string
    party_b?: string
    party_c?: string
    party_d?: string
    /** 客户特别交代（自由文本）：拼进审查 prompt，决定建议方向 */
    client_note?: string
    /** 客户诉求要点（chip 拆分后的结构化留存） */
    client_demands?: string[]
    /** 我方单位全名：立场方向的语义锚点（party_a/b 只是文档里的位置） */
    our_client_name?: string
    /** AI 判断我方立场的依据，供律师核对 */
    stance_basis?: string
  },
): Promise<ReviewTaskStatus> {
  return reviewApi()
    .post(`${encodeURIComponent(taskId)}/confirm-party`, { json: payload })
    .json<ReviewTaskStatus>()
}

/* ============================================================
 * 划词直改（/api/v1/contract-review/direct-edit）
 *
 * 与上面的「任务式审查」不是同一套逻辑：没有 task_id、没有立场、
 * 没有全篇扫描与评估报告。律师框选一段 + 说一句要求 → 出候选 → 采纳落痕。
 * ============================================================ */


/**
 * 生成 2~3 条改写候选。**零副作用**：不写文件、不建任务。
 *
 * 之所以跟 apply 拆成两次请求：律师要能反复「换个说法再生成」，
 * 而文件在明确采纳之前必须原封不动。
 */
export async function suggestDirectEdit(payload: {
  contract_id: number
  subpath: string
  selection: string
  instruction: string
  model_name?: string
}): Promise<DirectEditSuggestResult> {
  const res: DirectEditSuggestResult = await reviewApi()
    .post('direct-edit/suggest', { json: payload })
    .json<DirectEditSuggestResult>()
  return res
}


/**
 * 采纳一条候选：后端用 DocxRevisionTool 写成 `<w:del>`/`<w:ins>` 并覆写原文件。
 *
 * `applied=false` 不是错误，是「选区原文在文档里已找不到」（被前一次改动
 * 破坏），调用方应提示律师重新框选，而不是弹报错。
 */
export async function applyDirectEdit(payload: {
  contract_id: number
  subpath: string
  selection: string
  suggested: string
}): Promise<DirectEditApplyResult> {
  const res: DirectEditApplyResult = await reviewApi()
    .post('direct-edit/apply', { json: payload })
    .json<DirectEditApplyResult>()
  return res
}
