import { toast } from 'sonner'

import { createApiClient } from '@/lib/api'
import type { BundleMat, CaseRow } from '../types'
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
const coreApi = createApiClient() // prefix = API_BASE_URL(/api/v1)

export async function searchCases(q: string, signal?: AbortSignal): Promise<CaseRow[]> {
  if (!q.trim()) return []
  return coreApi.get('cases/search', { searchParams: { q, limit: '10' }, signal }).json<CaseRow[]>()
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
  const unknownPageCount = (source?.pages ?? 0) <= 0
  const coversWholeSource = seg.pageStart === 1 && seg.pageEnd === source?.pages
  if (unknownPageCount || coversWholeSource) return { blob: original, degraded: false }

  const cut = await cutSegmentBlob(original, seg.name, seg.pageStart, seg.pageEnd)
  // 切不出来就让这一段退回整包字节：归案照常完成，事后再由调用方提示
  if (!cut) return { blob: original, degraded: true }
  return { blob: cut, degraded: false }
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
  /** 没能切成独立 PDF（退回整包上传）的分段数；>0 时归案本身仍然成功 */
  unsplitCount: number
}

/** 归案要绑的一段材料：段名 + 该段页码（1 起、含两端）+ 页码出自第几个来源素材 */
interface BundledSegment {
  name: string
  partIndex: number
  pageStart: number
  pageEnd: number
}

/**
 * 执行归案。
 *
 * @param opts.target       existing 追加已有案件 / new 新建
 * @param opts.caseId       target=existing 时必填
 * @param opts.caseName     target=new 时的案件名
 * @param opts.parties      { our, their } —— 建当事人用
 * @param opts.segments     [{ name, partIndex, pageStart, pageEnd }]
 * @param opts.sources      材料包的来源素材（BundleMat[]）：给出时按每份素材的
 *                          `pages` 判断「该段是否覆盖整份」，覆盖就省掉切分往返
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
  segments: BundledSegment[]
  sources?: BundleMat[]
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

  // ④ 把分段绑成材料：**每段上传它自己那几页的 PDF**
  //    同一来源素材会被多个分段读到（切页输入），所以按 partIndex 缓存原始字节，
  //    一份 164 页的卷宗只下载一次。逐段串行处理即可（切分很快），不引并发。
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
      await casesApi.post(`${caseId}/materials/bind`, {
        json: { items: [{ attachment_id: attId, category: 'party', type_name: seg.name, side: 'our' }] },
      })
      boundCount += 1
    } catch {
      /* 单份失败继续下一份 */
    }
  }

  // 降级是静默的（材料照样绑上），但律师得知道有几份点开还是整卷——
  // 否则「为什么这份证据也有 164 页」只能靠猜。
  if (unsplitCount > 0) {
    toast.warning(`部分材料未能切分（${unsplitCount} 份），已按整包上传`, { id: 'assign' })
  }

  return { caseId, caseName, contractId, boundCount, unsplitCount }
}
