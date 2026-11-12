import { createApiClient } from '@/lib/api'
import type { CaseRow } from '../types'
import { clientApi } from './client'
import { contractsApi } from './contracts'
import { inboxApi } from './inbox-packs'

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
