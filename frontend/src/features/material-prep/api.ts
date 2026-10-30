import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'
// isEmptyDraft 直连 ./draft/state 而非 barrel：经 barrel 会因 resolve → ../api 的
// 既有依赖形成 api ↔ draft 环（见 draft/index.ts 头注释）
import { isEmptyDraft } from './draft/state'
import { PACK_SOURCE_TYPES } from './constants'
import type {
  AssignInfo,
  CaseRow,
  ClientHit,
  DraftState,
  InboxMessage,
  InboxMessageDetail,
  OcrResult,
  PackStatus,
} from './types'

/**
 * 材料预处理对接的是后端收件箱（/api/v1/inbox）。
 * 每次上传（可多文件）会生成一条 manual_upload 来源的消息，即一个「材料包」。
 */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 客户/当事人检索（/api/v1/client/parties/search，精简字段，兼容证件档案为空的客户） */
export const clientApi = createApiClient({ prefix: '/api/v1/client' })
const pdfSplitApi = createApiClient({ prefix: '/api/v1/pdf-splitting' })

/** GET /pdf-splitting/jobs/{job_id} 的响应（生成物 PdfSplitJobOut）。
 *  后端已修复 OpenAPI 组件名冲突（此前该端点误挂 doc-converter 的 JobOut，
 *  缺 job_id / segments 字段），schema 与实际响应一致，直接取生成物。 */
type PdfSplitJobPayload = components['schemas']['PdfSplitJobOut']

/** POST /pdf-splitting/jobs 的响应（生成物 PdfSplitJobSubmitOut） */
type PdfSplitJobSubmit = components['schemas']['PdfSplitJobSubmitOut']

export async function createPdfSplitJob(file: File): Promise<string> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('template_key', 'filing_materials_v1')
  body.append('split_mode', 'content_analysis')
  body.append('ocr_profile', 'accurate')
  const result = await pdfSplitApi
    .post('jobs', { body, timeout: UPLOAD_TIMEOUT_MS })
    .json<PdfSplitJobSubmit>()
  return result.job_id
}

export async function getPdfSplitJob(jobId: string): Promise<PdfSplitJobPayload> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJobPayload>()
}

/**
 * 按关键字模糊检索当事人。
 * isOurClient 限定范围：委托人传 true（我方当事人）、对方当事人传 false。
 */
export async function searchClients(
  keyword: string,
  isOurClient: boolean,
  signal?: AbortSignal,
): Promise<ClientHit[]> {
  return clientApi
    .get('parties/search', {
      searchParams: { keyword, is_our_client: isOurClient ? 'true' : 'false' },
      signal,
    })
    .json<ClientHit[]>()
}

export async function listMaterialPacks(): Promise<InboxMessage[]> {
  return inboxApi
    .get('messages', {
      // limit 显式对齐服务端兜底默认（500）：收件箱持续增长，桌面仓库列表
      // 在超过该量级前需要真正的分页/筛选，而不是无限拉全量
      searchParams: { source_type: PACK_SOURCE_TYPES, has_attachments: 'true', limit: '500' },
    })
    .json<InboxMessage[]>()
}

export async function getPackDetail(id: number): Promise<InboxMessageDetail> {
  return inboxApi.get(`messages/${id}`).json<InboxMessageDetail>()
}

/** 删除材料包（收件箱消息）：后端先清理附件物理文件，再删 DB 记录。
 *  响应为生成物 MessageAckOut（{ok, message_id}） */
export async function deletePack(id: number): Promise<components['schemas']['MessageAckOut']> {
  return inboxApi.delete(`messages/${id}`).json()
}

/** 重命名材料包标题（收件箱消息 subject）。
 *  响应为生成物 MessageRenameOut（{ok, message_id, subject}） */
export async function renamePack(
  id: number,
  subject: string,
): Promise<components['schemas']['MessageRenameOut']> {
  return inboxApi.put(`messages/${id}`, { json: { subject } }).json()
}

export async function uploadPack(files: File[], subject?: string): Promise<InboxMessageDetail> {
  return inboxApi
    .post('messages/upload', {
      body: toFormData(files, subject),
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<InboxMessageDetail>()
}

/** 阅读器内追加材料：往现有材料包再收一批文件，返回更新后的详情 */
export async function appendPackFiles(id: number, files: File[]): Promise<InboxMessageDetail> {
  return inboxApi
    .post(`messages/${id}/attachments`, {
      body: toFormData(files),
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<InboxMessageDetail>()
}

/** 只打标（未拆分）时的最小回写载荷：后端把 draft_state 当不透明 JSON 存储，
 *  从未拆分过的包写 {status[, assign]} 即可，阅读器打开时会按材料重建完整草稿。
 *  用精确联合而非 Partial<DraftState> / unknown——只为这一条合法的窄载荷开口，
 *  其余调用方仍必须交完整 DraftState。 */
export type PackStatusPatch = Pick<DraftState, 'status' | 'assign'>

/** 保存拆分草稿（整份 DraftState，或 setPackStatusRemote 的最小打标载荷） */
export async function saveDraft(id: number, draft: DraftState | PackStatusPatch): Promise<void> {
  await inboxApi.put(`messages/${id}/draft`, { json: { draft } }).json()
}

/** 只打标材料包状态（不接归档 / 归案），保留已有 draft_state 的拆分内容 */
export async function setPackStatusRemote(
  id: number,
  status: PackStatus,
  assign?: AssignInfo,
): Promise<void> {
  const detail = await getPackDetail(id)
  // draft_state 在未拆分过的包上是空占位 {}（判别见 draft/state.ts），守卫式
  // 窄化而非 as 抹掉联合：空占位无内容可保留，只写 status / assign（与历史
  // 行为一致）；有效草稿整份带上，不丢 mats/segs/infos。
  const draft: DraftState | PackStatusPatch = isEmptyDraft(detail.draft_state)
    ? { status }
    : { ...detail.draft_state, status }
  await saveDraft(id, assign ? { ...draft, assign } : draft)
}

/** 框选取字：把页面图片交给 RapidOCR，返回归一化文字块 */
export async function ocrImage(image: Blob): Promise<OcrResult> {
  const fd = new FormData()
  fd.append('file', image, 'page.png')
  return inboxApi
    .post('ocr', { body: fd, timeout: UPLOAD_TIMEOUT_MS })
    .json<OcrResult>()
}

/** 搜索真实案件（归案 modal 用）；模块级建一次客户端，避免每次检索重复 create */
const coreApi = createApiClient() // prefix = API_BASE_URL(/api/v1)

export async function searchCases(q: string, signal?: AbortSignal): Promise<CaseRow[]> {
  if (!q.trim()) return []
  return coreApi.get('cases/search', { searchParams: { q, limit: '10' }, signal }).json<CaseRow[]>()
}

const bytesCache = new Map<string, Promise<ArrayBuffer>>()

/**
 * 取附件字节（带鉴权），按 messageId:partIndex 缓存。供 PDF.js 渲染、OCR 取字、云端识别上传。
 *
 * 返回的是缓存的 buffer 本体（调用方会反复复用：每页渲染、OCR、识别上传各取一次）。
 * 若某个调用方会把 buffer **transfer** 给 worker 导致它被 detach（PDF.js 的
 * getDocument({ data }) 就是），请在该调用方内部先拷贝再传——不要在这里拷，
 * 否则 92 页的材料会凭空多拷 92 次。详见 lib/pdf.ts 的 loadPdfDocument。
 */
export function fetchAttachmentBytes(messageId: number, partIndex: number): Promise<ArrayBuffer> {
  const key = `${messageId}:${partIndex}`
  const hit = bytesCache.get(key)
  if (hit) return hit
  const p = inboxApi
    .get(`messages/${messageId}/attachments/${partIndex}/preview`)
    .then((res) => res.arrayBuffer())
    .catch((e) => {
      bytesCache.delete(key)
      throw e
    })
  bytesCache.set(key, p)
  return p
}

export function clearBytesCache(): void {
  bytesCache.clear()
}

function toFormData(files: File[], subject?: string): FormData {
  const fd = new FormData()
  if (subject) fd.append('subject', subject)
  for (const f of files) fd.append('files', f, f.name)
  return fd
}

/* ============ 客户上传链接（/api/v1/inbox/upload-links） ============ */

/** 链接列表行（生成物 UploadLinkOut；token 明文绝不在列表出现） */
export type UploadLinkRow = components['schemas']['UploadLinkOut']

/** 创建/轮换响应（生成物 UploadLinkCreatedOut；token 明文仅此一次） */
export type UploadLinkCreated = components['schemas']['UploadLinkCreatedOut']

export async function createUploadLink(payload: {
  title: string
  note?: string
  client_name?: string
  contract_id?: number | null
  expires_days?: number
}): Promise<UploadLinkCreated> {
  return inboxApi.post('upload-links', { json: payload }).json<UploadLinkCreated>()
}

export async function listUploadLinks(): Promise<UploadLinkRow[]> {
  return inboxApi.get('upload-links').json<UploadLinkRow[]>()
}

export async function revokeUploadLink(id: number): Promise<UploadLinkRow> {
  return inboxApi.post(`upload-links/${id}/revoke`).json<UploadLinkRow>()
}

/**
 * 彻底删除链接（从列表消失）。与作废的区别：作废只改状态、记录留着可审计；
 * 删除是真的不显示了，用于清理已作废的历史。
 *
 * 后端限**创建人本人或管理员**（其余返回 404），已收材料包不受影响
 * （`InboxMessage.upload_link` 是 SET_NULL，只置空来源指针）。
 */
export async function deleteUploadLink(id: number): Promise<void> {
  await inboxApi.delete(`upload-links/${id}`)
}

export async function rotateUploadLink(id: number): Promise<UploadLinkCreated> {
  return inboxApi.post(`upload-links/${id}/rotate`).json<UploadLinkCreated>()
}

/** 组装客户分享 URL：公开页路由 /u/:token，用当前站点 origin（公网/内网各自成立） */
export function buildShareUrl(token: string): string {
  return `${window.location.origin}/u/${token}`
}

/* ============ 项目（委托合同）检索：生成链接时绑定项目用 ============ */

/** 跨 feature import workbench 被禁止，这里按需直连同源端点做最小投影 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })

/** 合同检索命中行（生成物 ContractOut 的消费子集；id 覆写为必有） */
export type ContractHit = Pick<
  components['schemas']['ContractOut'],
  'name' | 'filing_number'
> & { id: number }

export async function searchContracts(q: string, signal?: AbortSignal): Promise<ContractHit[]> {
  if (!q.trim()) return []
  const res = await contractsApi
    .get('contracts', {
      searchParams: { search: q, slim: 'true', include_facets: 'false', page: '1', page_size: '10' },
      signal,
    })
    .json<{ items: ContractHit[] }>()
  return res.items ?? []
}

// ───────────────────────── 归案（建案 + 材料落地）─────────────────────────

/**
 * 归案：把材料包里的分段变成某个案件的真实材料。
 *
 * ═══ 为什么之前「点归案没反应」═══
 * 原实现只做两件事：把 assign 写进 draft_state、弹一句「已归案」。
 * 类型注释写着「办案端据此建案」—— 但办案端从来没有实现这个动作，
 * 于是「新建案件」这个选项形同虚设：用户以为建了，列表里什么也没有。
 *
 * 现在归案是**真动作**：
 *   ① 目标案件已有 → 直接把分段绑成材料
 *   ② 目标是新案件 → 先建合同+案件，再把分段绑进去
 *   ③ 最后把材料包标成 done（已归案），让它从「待处理」消失
 */

// ⚠️ contractsApi 在本文件上方已声明（项目检索用），这里**不能再声明一次** ——
//    重复 const 是 SyntaxError，整个模块加载失败，页面直接白屏
//    （实测：打开材料包看到「页面出错了」，控制台报
//     Identifier 'contractsApi' has already been declared）。
// clientApi / contractsApi 本文件上方已声明，复用即可（重复声明会 SyntaxError 白屏）
const casesApi = createApiClient({ prefix: '/api/v1/cases' })

/** 归案时上传一个分段并返回附件 id */
async function uploadSegment(caseId: number, blob: Blob, name: string): Promise<number | null> {
  const fd = new FormData()
  fd.append('files', new File([blob], name, { type: 'application/pdf' }))
  try {
    const r = await casesApi
      .post(`${caseId}/materials/upload`, { body: fd, timeout: 300_000 })
      .json<{ attachment_ids?: number[] }>()
    return r?.attachment_ids?.[0] ?? null
  } catch {
    return null
  }
}

/**
 * 把一段材料从后端切出来（原始 PDF 的 page_start..page_end）。
 *
 * 用浏览器端 pdf-lib 做不到（没装依赖），这里走后端已有的分段导出：
 * /pdf-splitting/jobs/{job_id}/download 会给整包 zip，但归案时我们手里
 * 只有 draft 的分段信息。
 *
 * 现实做法：**整包上传一次**，按分段页范围在前端做标记。
 * 后端 CaseMaterial 只需要一个附件 + 类型名，页范围是展示层的概念。
 * 所以这里上传原始附件整份，再按分段建多条材料记录指向同一附件。
 */
async function fetchOriginalBlob(messageId: number, partIndex: number): Promise<Blob | null> {
  try {
    // 走既有 inboxApi（已带 JWT 与超时），不手搓 fetch
    const res = await inboxApi.get(`messages/${messageId}/attachments/${partIndex}/download`, {
      timeout: 120_000,
    })
    return await res.blob()
  } catch {
    return null
  }
}

/** 建客户（归案生成合同时要用） */
async function ensureClient(p: {
  name: string
  isOur: boolean
  idNumber?: string
}): Promise<number | null> {
  try {
    const r = await clientApi
      .post('clients', {
        json: {
          name: p.name,
          client_type: p.name.length > 12 || /公司|银行|支行|分行|律所/.test(p.name) ? 'legal' : 'natural',
          is_our_client: p.isOur,
          id_number: p.idNumber ?? '',
          address: '',
          legal_representative: p.isOur ? '某某' : '',
        },
      })
      .json<{ id?: number }>()
    return r?.id != null ? Number(r.id) : null
  } catch {
    return null
  }
}

/** 当前律师 id */
export async function currentLawyerId(): Promise<number> {
  const orgApi = createApiClient({ prefix: '/api/v1/organization' })
  try {
    const me = await orgApi.get('me').json<{ id?: number }>()
    if (me?.id != null) return Number(me.id)
  } catch {
    /* 走兜底 */
  }
  const list = await orgApi.get('lawyers').json<{ id: number }[] | { items?: { id: number }[] }>()
  const arr = Array.isArray(list) ? list : (list.items ?? [])
  if (arr[0]?.id != null) return Number(arr[0].id)
  throw new Error('无法确定当前律师，请重新登录')
}

export interface AssignResult {
  caseId: number
  caseName: string
  contractId: number | null
  boundCount: number
}

/**
 * 执行归案。
 *
 * @param opts.target       existing 追加已有案件 / new 新建
 * @param opts.caseId       target=existing 时必填
 * @param opts.caseName     target=new 时的案件名
 * @param opts.parties      { our, their } —— 建当事人用
 * @param opts.segments     [{ name, partIndex, pageStart, pageEnd }]
 */
export async function assignPack(opts: {
  messageId: number
  target: 'existing' | 'new'
  caseId?: number
  caseName?: string
  court?: string
  cause?: string
  targetAmount?: string
  parties: { our: string; their: string }
  segments: { name: string; partIndex: number; pageStart: number; pageEnd: number }[]
}): Promise<AssignResult> {
  let caseId = opts.caseId ?? 0
  let caseName: string
  let contractId: number | null = null

  if (opts.target === 'new') {
    const me = await currentLawyerId()

    // ① 客户：委托人（我方）+ 对方当事人
    const ourId = opts.parties.our ? await ensureClient({ name: opts.parties.our, isOur: true }) : null
    const theirIds: number[] = []
    for (const n of opts.parties.their.split(/[、,，]/).map((x) => x.trim()).filter(Boolean)) {
      const id = await ensureClient({ name: n, isOur: false })
      if (id) theirIds.push(id)
    }

    // ② 合同（委托关系）—— 失败不阻断
    try {
      const c = await contractsApi
        .post('contracts/full', {
          json: {
            name: `${opts.caseName ?? '新材料'}·委托合同`,
            case_type: 'civil',
            status: 'active',
            start_date: new Date().toISOString().slice(0, 10),
            // ⚠️ 必须给代理阶段：不给的话详情页显示
            //    「合同没有勾选代理阶段，也还没有立案的程序」，
            //    左栏的程序节点条也画不出来。
            representation_stages: ['first_trial', 'second_trial', 'enforcement'],
            lawyer_ids: [me],
            fee_mode: 'FIXED',
            fixed_amount: 5000,
            parties: ourId ? [{ client_id: ourId, role: 'PRINCIPAL' }] : [],
            cases: [],
          },
        })
        .json<{ id?: number }>()
      contractId = c?.id != null ? Number(c.id) : null
    } catch {
      /* 合同建不出来也能归案，只是 OA 立案用不了 */
    }

    // ③ 案件：一次建齐 案件 + 当事人 + 主办律师 + 管辖法院
    const created = await casesApi
      .post('cases/full', {
        json: {
          case: {
            name: opts.caseName ?? '新材料归案案件',
            case_type: 'civil',
            status: 'active',
            current_stage: 'first_trial',
            cause_of_action: opts.cause ?? '',
            target_amount: opts.targetAmount ?? null,
          },
          parties: [
            ...(ourId ? [{ client_id: ourId, legal_status: 'plaintiff' }] : []),
            ...theirIds.map((id) => ({ client_id: id, legal_status: 'defendant' })),
          ],
          assignments: [{ lawyer_id: me }],
          supervising_authorities: opts.court
            ? [{ name: opts.court, authority_type: 'trial' }]
            : [],
          logs: [],
          case_numbers: [],
        },
      })
      .json<{ id?: number; name?: string }>()
    caseId = Number(created?.id)
    caseName = created?.name ?? (opts.caseName ?? '')
    if (!Number.isFinite(caseId)) throw new Error('建案失败：后端未返回案件 id')
  } else {
    const c = await casesApi.get(`cases/${caseId}`).json<{ name?: string }>()
    caseName = c?.name ?? ''
  }

  // ④ 把分段绑成材料
  //    说明：CaseMaterial 只认「附件 + 类型名」，页范围是展示层概念。
  //    所以整包附件上传一次，再按分段建多条材料记录指向同一附件 ——
  //    这与真实业务流程一致（原始扫描件就那一份，分类是律所打的标签）。
  let boundCount = 0
  for (const seg of opts.segments) {
    const blob = await fetchOriginalBlob(opts.messageId, seg.partIndex)
    if (!blob) continue
    const attId = await uploadSegment(caseId, blob, `${seg.name}.pdf`)
    if (attId == null) continue
    try {
      await casesApi.post(`${caseId}/materials/bind`, {
        json: { items: [{ attachment_id: attId, category: 'party', type_name: seg.name, side: 'our' }] },
      })
      boundCount += 1
    } catch {
      /* 单份失败继续下一份 */
    }
  }

  return { caseId, caseName, contractId, boundCount }
}
