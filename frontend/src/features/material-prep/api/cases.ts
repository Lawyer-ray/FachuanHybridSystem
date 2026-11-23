import { toast } from 'sonner'

import { createApiClient } from '@/lib/api'
import type { BundleMat, CaseRow } from '../types'
import { bindProvenance } from './assign-provenance'
import { clientApi } from './client'
import { contractsApi } from './contracts'
import { inboxApi } from './inbox-packs'
import { extractPdfPages } from './pdf-split'

/**
 * 案件检索 / 建案 / 归案落地（/api/v1/cases）。
 *
 * 归案（建案 + 材料落地）整条链路放在这里：它跨越 cases / client / contracts
 * 三个后端域，而「材料包里的分段 → 案件里的材料」这个动作只有一个入口
 * （AssignModal → use-assign-launch），拆开就只剩互相调用的碎片。
 */

/** 搜索真实案件（归案 modal 用）；模块级建一次客户端，避免每次检索重复 create */
// 路径必须带后端挂载前缀：api_v1.add_router('/cases', …) + @router.get('/cases/search')
// → 真实地址 /api/v1/cases/cases/search（生成物 api-schema.d.ts 里唯一存在的 search 路径）
const coreApi = createApiClient() // prefix = API_BASE_URL(/api/v1)

// ────────────────────── 归案自动建合同的产品口径 ──────────────────────
// 这些值由前端单方面决定并直接写进后端库，属「临时兜底」而非契约字段：
// 后端没给归案时填什么，故前端选了一组固定值让 OA 立案有据可依。
// 真要改口径（尤其费率）必须产品确认后再改，不要就地调数字。

/** 归案建合同用的案件类型（合同与案件同一口径） */
const ASSIGN_CASE_TYPE = 'civil'
/** 归案建合同：固定收费模式 */
const ASSIGN_CONTRACT_FEE_MODE = 'FIXED'
/** 归案建合同：固定收费金额（元）。产品口径，非真实计费依据 */
const ASSIGN_CONTRACT_FIXED_AMOUNT = 5000
/** 归案建合同必填代理阶段：空着详情页与左栏程序节点条都画不出来 */
const ASSIGN_CONTRACT_STAGES = ['first_trial', 'second_trial', 'enforcement']

export async function searchCases(q: string, signal?: AbortSignal): Promise<CaseRow[]> {
  if (!q.trim()) return []
  return coreApi.get('cases/cases/search', { searchParams: { q, limit: '10' }, signal }).json<CaseRow[]>()
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

// ⚠️ contractsApi 在 ./contracts 声明（项目检索用），这里 import 复用 ——
//    过去在单文件里重复声明一次是 SyntaxError，整个模块加载失败，页面直接白屏
//    （实测：打开材料包看到「页面出错了」，控制台报
//     Identifier 'contractsApi' has already been declared）。
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
 * 取材料包里某个来源素材的整份原始字节。
 *
 * 归案时拿它当切页的输入；切分失败时也拿它整包兜底上传。
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

/** 按页范围切出这一段的 PDF；失败回 null（调用方降级为整包上传） */
async function cutSegmentBlob(
  blob: Blob,
  name: string,
  pageStart: number,
  pageEnd: number,
): Promise<Blob | null> {
  try {
    return await extractPdfPages(blob, name, pageStart, pageEnd)
  } catch {
    return null
  }
}

/**
 * 一个分段该上传哪份字节。
 *
 * ═══ 为什么要切 ═══
 * 后端 CaseMaterial 只认「附件 + 类型名」，所以早先的做法是整包上传一次、
 * 每段建一条材料记录指向同一附件 —— 结果 36 段材料点开都是**完整的 164 页**，
 * 律师开庭时找不到具体材料。现在按分段页范围真切，每份材料就是它自己那几页。
 *
 * 两个不切的合法例外：
 * ① 该段恰好覆盖整份素材（1..pages 全部页）—— 切与不切内容完全一样，
 *    多跑一次切分只换来一次无谓往返，直接上传原始字节；
 * ② 来源素材是图片/Office 转出（`pages` 未知 / 为 0）—— 页范围不可信，
 *    宁可整包也不拿错的页号去切。
 * ②之外切不出来（端点报错、PDF 损坏）也算降级，要计数并提示：
 * 材料照样绑得上，但律师得知道有几份点开还是整卷。
 */
async function segmentUploadBlob(
  seg: BundledSegment,
  original: Blob,
  source: BundleMat | undefined,
): Promise<{ blob: Blob; degraded: boolean }> {
  // 页数不可信（读不出来时兜底成 1）→ 不能拿它判「是否覆盖整份」。
  //
  // 真实后果（核查实测）：一份 164 页的卷宗，页数读取失败 → `pages: 1`，
  // 于是任意 `pageStart=1,pageEnd=1` 的段都被判成「覆盖整份」→ 把 68MB
  // 整卷当 1 页材料上传，而且 degraded:false 不提示。
  // 现在 pagesUnknown 为真时直接走「不切页」分支（与页数=0 同口径），
  // 结果与原来一致（整包传）但语义诚实，且不会被误当成真实页数。
  const unknownPageCount = (source?.pages ?? 0) <= 0 || source?.pagesUnknown === true
  const coversWholeSource = !unknownPageCount && seg.pageStart === 1 && seg.pageEnd === source?.pages
  if (unknownPageCount || coversWholeSource) return { blob: original, degraded: false }

  const cut = await cutSegmentBlob(original, seg.name, seg.pageStart, seg.pageEnd)
  // 切不出来就让这一段退回整包字节：归案照常完成，事后再由调用方提示
  if (!cut) return { blob: original, degraded: true }
  return { blob: cut, degraded: false }
}

/** 建客户（归案生成合同时要用） */
async function ensureClient(p: { name: string; isOur: boolean }): Promise<number | null> {
  try {
    const r = await clientApi
      .post('clients', {
        json: {
          name: p.name,
          client_type: p.name.length > 12 || /公司|银行|支行|分行|律所/.test(p.name) ? 'legal' : 'natural',
          is_our_client: p.isOur,
          id_number: '',
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
  /** 没能切成独立 PDF（退回整包上传）的分段数；>0 时归案本身仍然成功 */
  unsplitCount: number
}

/** 归案要绑的一段材料：段名 + 该段页码（1 起、含两端）+ 页码出自第几个来源素材 + 段标识 */
interface BundledSegment {
  name: string
  partIndex: number
  pageStart: number
  pageEnd: number
  /**
   * 草稿里的段 id（`Segment.id`）。归案时作为 `source_segment_ref` 传给后端，
   * 起草 RAG 据此找回**律师核对过的那一段**预处理 Markdown；缺了它只能按包级
   * 文件哈希匹配，段级对不上。
   */
  segmentRef: string
}

/** 归案的全部入参 */
export interface AssignPackOptions {
  /** 材料包消息 id：取原始附件字节，并作为归案溯源 `source_message_id` */
  messageId: number
  /** existing 追加已有案件 / new 新建 */
  target: 'existing' | 'new'
  /** target=existing 时必填 */
  caseId?: number
  /** target=new 时的案件名 */
  caseName?: string
  court?: string
  cause?: string
  targetAmount?: string
  /** { our, their } —— 建当事人用 */
  parties: { our: string; their: string }
  /** [{ name, partIndex, pageStart, pageEnd, segmentRef }] */
  segments: BundledSegment[]
  /**
   * 材料包的来源素材（BundleMat[]）：给出时按每份素材的 `pages` 判断
   * 「该段是否覆盖整份」，覆盖就省掉切分往返
   */
  sources?: BundleMat[]
}

/** 建案三步的产物：绑段要的定位键，以及结果里要回报的合同 id 与案件名 */
interface CreatedCase {
  caseId: number
  caseName: string
  contractId: number | null
}

/**
 * 归案的第 ①②③ 段：客户（委托人 + 对方）→ 合同 → 案件。
 *
 * 三步串成一条链是因为后一步要用前一步的 id（当事人挂客户、案件挂当事人），
 * 不能并发。合同失败**不阻断**归案：只是 OA 立案用不了，材料照样落得下去。
 * `target='existing'` 时一步都不建，只按 id 取回案件名（结果里要回报）。
 */
async function createCaseForAssign(
  opts: Pick<AssignPackOptions, 'target' | 'caseId' | 'caseName' | 'court' | 'cause' | 'targetAmount' | 'parties'>,
): Promise<CreatedCase> {
  if (opts.target !== 'new') {
    const caseId = opts.caseId ?? 0
    const c = await casesApi.get(`cases/${caseId}`).json<{ name?: string }>()
    return { caseId, caseName: c?.name ?? '', contractId: null }
  }

  let contractId: number | null = null
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
          case_type: ASSIGN_CASE_TYPE,
          status: 'active',
          start_date: new Date().toISOString().slice(0, 10),
          // ⚠️ 必须给代理阶段：不给的话详情页显示
          //    「合同没有勾选代理阶段，也还没有立案的程序」，
          //    左栏的程序节点条也画不出来。
          representation_stages: ASSIGN_CONTRACT_STAGES,
          lawyer_ids: [me],
          fee_mode: ASSIGN_CONTRACT_FEE_MODE,
          fixed_amount: ASSIGN_CONTRACT_FIXED_AMOUNT,
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
          case_type: ASSIGN_CASE_TYPE,
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
  const caseId = Number(created?.id)
  if (!Number.isFinite(caseId)) throw new Error('建案失败：后端未返回案件 id')
  return { caseId, caseName: created?.name ?? (opts.caseName ?? ''), contractId }
}

/**
 * 归案的第 ④ 段：把分段绑成案件材料——**每段上传它自己那几页的 PDF**。
 *
 * 同一来源素材会被多个分段读到（切页输入），所以按 partIndex 缓存原始字节，
 * 一份 164 页的卷宗只下载一次。逐段串行处理即可（切分很快），不引并发。
 * 单段出问题只影响自己：取不到字节就跳过、上传拿不到附件 id 就跳过、
 * 绑定请求失败继续下一份（已绑上的不回滚）。
 */
async function bindSegments(
  opts: Pick<AssignPackOptions, 'messageId' | 'segments' | 'sources'>,
  caseId: number,
): Promise<{ boundCount: number; unsplitCount: number }> {
  const sourceCache = new Map<number, Blob | null>()
  const sourceByPart = new Map((opts.sources ?? []).map((mat) => [mat.partIndex, mat]))
  let boundCount = 0
  let unsplitCount = 0
  for (const seg of opts.segments) {
    if (!sourceCache.has(seg.partIndex)) {
      sourceCache.set(seg.partIndex, await fetchOriginalBlob(opts.messageId, seg.partIndex))
    }
    const original = sourceCache.get(seg.partIndex)
    if (!original) continue
    const { blob, degraded } = await segmentUploadBlob(seg, original, sourceByPart.get(seg.partIndex))
    if (degraded) unsplitCount += 1
    const attId = await uploadSegment(caseId, blob, `${seg.name}.pdf`)
    if (attId == null) continue
    try {
      // 带上溯源：起草 RAG 据此消费预处理 Markdown，而不是对同一份 PDF 再抽一遍纯文本
      await casesApi.post(`${caseId}/materials/bind`, {
        json: {
          items: [{
            attachment_id: attId,
            category: 'party',
            type_name: seg.name,
            side: 'our',
            ...bindProvenance(opts.messageId, seg.segmentRef),
          }],
        },
      })
      boundCount += 1
    } catch {
      /* 单份失败继续下一份 */
    }
  }
  return { boundCount, unsplitCount }
}

/**
 * 执行归案：建案（①②③）→ 绑段（④）→ 报降级。
 *
 * 前三段在 `createCaseForAssign`、第四段在 `bindSegments`，这里只排次序；
 * 唯一留在编排层的判断是「有降级要提示」——它属于整次归案的收尾，不是绑段本身。
 */
export async function assignPack(opts: AssignPackOptions): Promise<AssignResult> {
  const { caseId, caseName, contractId } = await createCaseForAssign(opts)
  const { boundCount, unsplitCount } = await bindSegments(opts, caseId)

  // 降级是静默的（材料照样绑上），但律师得知道有几份点开还是整卷——
  // 否则「为什么这份证据也有 164 页」只能靠猜。
  if (unsplitCount > 0) {
    toast.warning(`部分材料未能切分（${unsplitCount} 份），已按整包上传`, { id: 'assign' })
  }

  return { caseId, caseName, contractId, boundCount, unsplitCount }
}
