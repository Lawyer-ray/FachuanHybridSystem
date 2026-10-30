import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

/**
 * 演示模式 —— 一键把场景 2 的演示数据铺好。
 *
 * ═══ 为什么需要它 ═══
 * 演示/录屏时不该让演示者手找文件、手建案件、手填当事人：
 *   ① 现场翻文件夹找 mock PDF —— 打断节奏，还容易选错
 *   ② 手动建案要填七八个字段 —— 演示重点不是表单
 *   ③ 建完案还要自己上传材料、自己归案 —— 一长串机械操作
 * 一个按钮把「整包 PDF 进收件箱 + 合同/案件/当事人已建好」做完，
 * 律师接着走**真正需要判断的那几步**：分段复核 → 归案 → 立案。
 *
 * ═══ 边界（很重要）═══
 * 演示数据全部**新建**，名字带 `[演示]` 前缀：
 *   · 绝不改、不删任何已有案件
 *   · 重复点会建出多套（各自独立，互不干扰）
 */

const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const clientApi = createApiClient({ prefix: '/api/v1/client' })
/** 合同+案件一次性创建（后端 ContractWithCasesIn），比连调两个接口稳 */
const fullContractApi = createApiClient({ prefix: '/api/v1/contracts' })

/** 演示可选的三个场景，与 public/demo-materials/ 下的文件一一对应 */
export interface DemoScenario {
  key: 'first_trial' | 'consumer_loan' | 'appeal'
  title: string
  point: string
  file: string
  /** 案件阶段：决定整包分段用哪个模板（一审 / 二审） */
  stage: string
  subject: string
  cause: string
  plaintiff: { name: string; legalRep: string; address: string }
  defendants: { name: string; idNumber: string; address: string }[]
  targetAmount: string
}

/**
 * ═══ 三个场景的共同前提：包里装的是「客户端送来的材料」═══
 *
 * 这一点最容易搞错，写在这里免得再错：
 *   客户/银行送来的整包里**没有起诉状、没有证据清单、没有答辩状、
 *   没有送达地址确认书** —— 那些都是律所拿到材料之后**自己产出**的。
 *   起诉状要律师写、证据清单要律师编、答辩状要针对上诉理由逐条拟。
 *
 * 真实卷宗可以验证：银行的「证据材料」目录里是合同/凭证/明细/流水/催收，
 * 而「民事起诉状.docx」放在律所自己的目录里。
 *
 * 所以演示按钮传进来的包只含原始材料；起诉状等文书的生成，
 * 走「要素式转换 / 文书起草」那些下游功能 —— 那才是产品真正的价值点。
 */
export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    key: 'consumer_loan',
    title: '消费贷批量（5 笔提款）',
    point: '一份框架协议 + 5 笔提款，每笔「合同→凭证→明细」三件套 —— 最能体现批量能力',
    file: '/demo-materials/1-第一次提交证据（整包扫描件）.pdf',
    stage: 'first_trial',
    subject: '系列借款合同纠纷',
    cause: '金融借款合同纠纷',
    plaintiff: {
      name: '[演示] 某某银行股份有限公司某某分行',
      legalRep: '陈某某',
      address: '某某大道 100 号某某大厦（虚构）',
    },
    defendants: [
      {
        // 证件号为示例段位且**校验位不合法**（末位刻意写错），
        // 确保任何校验器都会判定为无效号，不会与真实身份撞上。
        name: '[演示] 周某某',
        idNumber: '110101199007150001',
        address: '某某镇某某路 8 号（虚构地址）',
      },
    ],
    targetAmount: '49263.55',
  },
  {
    key: 'first_trial',
    title: '银行移交材料（起诉·房贷单笔）',
    point: '银行档案里的原始材料：借款合同 / 借据 / 流水 / 催收 / 身份材料',
    file: '/demo-materials/银行移交材料包（起诉用·整包扫描件）.pdf',
    stage: 'first_trial',
    subject: '金融借款合同纠纷',
    cause: '金融借款合同纠纷',
    plaintiff: {
      name: '[演示] 某某银行股份有限公司某某城南支行',
      legalRep: '陈某某',
      address: '某某大道 200 号某某大厦 1-3 层（虚构）',
    },
    defendants: [
      { name: '[演示] 谭某某', idNumber: '110101199305110008', address: '某某路 18 号（虚构）' },
      { name: '[演示] 梁某某', idNumber: '110101199508050009', address: '某某村 6 组（虚构）' },
    ],
    targetAmount: '999722.11',
  },
  {
    key: 'appeal',
    title: '二审收案（对方上诉）',
    point: '法院送达的一审判决书 + 对方提交的上诉状 + 一审卷宗',
    file: '/demo-materials/二审收案材料包（整包扫描件）.pdf',
    stage: 'second_trial',
    subject: '金融借款合同纠纷（二审）',
    cause: '金融借款合同纠纷',
    plaintiff: {
      name: '[演示] 某某银行股份有限公司某某城南支行',
      legalRep: '陈某某',
      address: '某某大道 200 号某某大厦 1-3 层（虚构）',
    },
    defendants: [
      { name: '[演示] 吴某某', idNumber: '110101199101010005', address: '某某街道某某路（虚构）' },
    ],
    targetAmount: '437500.00',
  },
]

export const DEMO_TAG = '[演示]'

/**
 * 演示材料包的标题前缀。用于识别「这包是演示生成的」——
 * 清理时按它匹配，不碰用户自己上传的材料包。
 */
const DEMO_SUBJECT_HINTS = ['银行移交材料', '消费贷批量', '二审收案']

/** 这一包是不是演示生成的（按标题前缀判断，不看 id） */
function isDemoPack(subject: string | null | undefined): boolean {
  const s = subject ?? ''
  return DEMO_SUBJECT_HINTS.some((h) => s.includes(h))
}

/**
 * 清空全部演示数据 —— 让「演示」按钮变成**可重复**的动作。
 *
 * ═══ 为什么必须重置 ═══
 * 不重置的话点几次就有几套：5 件同名案件、6 个同名材料包、一堆已拆好的草稿。
 * 演示现场最怕这个 —— 你点开列表看到 5 个「谭某某」，不知道该讲哪个；
 * 或者上一轮拆到一半的材料包还躺在「待处理」，状态混在一起。
 *
 * 演示的正确语义是：**每次点都从零开始**，律师看到的是干净初始态。
 *
 * ═══ 边界 ═══
 * 只删两类：名字带 `[演示]` 的案件、标题命中演示场景的材料包。
 * 用户自己的真实案件/材料包一个都不碰 —— 匹配是按名字前缀，
 * 不是按 id 范围，也不是「清空表」。
 */
export async function resetDemoData(): Promise<{ cases: number; packs: number }> {
  const contractApi = createApiClient({ prefix: '/api/v1/contracts' })
  const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

  // ① 演示案件（顺带记下它们的合同 id，一起删）
  const list = await casesApi.get('cases').json<components['schemas']['CaseOut'][]>()
  const demoCases = list.filter((c) => c.name?.startsWith(DEMO_TAG))
  const contractIds = new Set<number>()
  for (const c of demoCases) {
    if (c.contract_id != null) contractIds.add(Number(c.contract_id))
    await casesApi.delete(`cases/${Number(c.id)}`).catch(() => {
      /* 已删 / 无权限都不阻断后续清理 */
    })
  }

  // ② 演示合同（案件删掉后合同还在，留着会越积越多）
  for (const id of contractIds) {
    await contractApi.delete(`contracts/${id}`).catch(() => {
      /* 合同可能被别的案件引用，删不掉就留着 */
    })
  }

  // ③ 演示材料包（收件箱消息）
  type Msg = { id: number; subject?: string | null }
  const raw = await inboxApi
    .get('messages', { searchParams: { limit: '200', source_type: 'manual_upload' } })
    .json<Msg[] | { items?: Msg[] }>()
  const msgs = Array.isArray(raw) ? raw : (raw.items ?? [])
  let removedPacks = 0
  for (const m of msgs) {
    if (!isDemoPack(m.subject)) continue
    try {
      await inboxApi.delete(`messages/${Number(m.id)}`)
      removedPacks += 1
    } catch {
      /* 单条删不掉继续删下一条 */
    }
  }

  return { cases: demoCases.length, packs: removedPacks }
}

/**
 * 铺一套演示数据。
 *
 * 顺序有讲究：**先建客户**，因为合同的委托方要引用 client_id。
 * 合同+案件用 `/contracts/contracts/full` 一次建完 —— 连调两个接口的话，
 * 中途失败会留下「有合同没案件」的半成品，演示时看着像 bug。
 */
export async function seedDemoScenario(sc: DemoScenario): Promise<{
  caseId: number
  contractId: number | null
  caseName: string
}> {
  // 0. 当前律师 id —— contract full 要求必须有主办律师
  const me = await currentLawyerId()

  // ① 客户：原告（我方）+ 各被告
  const plaintiffClientId = await ensureClient({
    name: sc.plaintiff.name,
    clientType: 'legal',
    isOurClient: true,
    // ⚠️ 身份证号/统一社会信用代码在后端有唯一约束，且**已删除的客户仍占用**。
    //    用时间戳派生，保证每次演示都建得出新客户（重复点不会撞
    //    「具有身份证号码或统一社会信用代码的当事人已存在」）。
    idNumber: `00000000DEMO${String(Date.now()).slice(-6)}`,
    address: sc.plaintiff.address,
    legalRep: sc.plaintiff.legalRep,
  })

  // 被告也用时间戳派生序号，理由同上（同一份演示重复跑不该撞唯一约束）
  const stamp = String(Date.now()).slice(-4)
  const defendantIds: number[] = []
  for (const [i, d] of sc.defendants.entries()) {
    const id = await ensureClient({
      name: d.name,
      clientType: 'natural',
      isOurClient: false,
      // 保留原号前 10 位（属地+生日）便于辨认，末 4 位换成时间戳
      idNumber: `${d.idNumber.slice(0, 10)}${stamp}${String(i).padStart(2, '0')}`.slice(0, 18),
      address: d.address,
    })
    if (id) defendantIds.push(id)
  }

  // ② 合同 + 案件（一次建完）
  const caseName = `${DEMO_TAG} ${sc.defendants.map((d) => d.name.replace(`${DEMO_TAG} `, '')).join('、')}${sc.subject}`
  const body = {
    name: `${DEMO_TAG} ${sc.plaintiff.name.replace(`${DEMO_TAG} `, '')}诉讼委托`,
    case_type: 'civil',
    status: 'active',
    start_date: today(),
    representation_stages: [sc.stage],
    // ⚠️ 三个都是后端硬校验，缺一个就 422：
    //    lawyer_ids 空数组 → 「至少需要指派一个律师」
    //    fee_mode=FIXED 不给 fixed_amount → 「固定收费需填写金额」
    lawyer_ids: [me],
    fee_mode: 'FIXED',
    fixed_amount: 5000,
    parties: plaintiffClientId ? [{ client_id: plaintiffClientId, role: 'PRINCIPAL' }] : [],
    cases: [
      {
        name: caseName,
        case_type: 'civil',
        status: 'active',
        current_stage: sc.stage,
        cause_of_action: sc.cause,
        target_amount: sc.targetAmount,
        start_date: today(),
        // 被告挂到案件上（合同的 parties 只记委托方）
        parties: defendantIds.map((id) => ({ client_id: id, legal_status: 'defendant' })),
      },
    ],
  }

  const created = await fullContractApi
    .post('contracts/full', { json: body })
    .json<{ id?: number; case_count?: number }>()

  const contractId = created?.id != null ? Number(created.id) : null

  // ⚠️ 返回体只有 `case_count`，**没有 case id**（实测）。
  //    所以建完必须按名字回查一次。不猜、不跳过：查不到就报错，
  //    否则后续所有步骤都会对着一个不存在的 caseId 调接口，
  //    表现是「案件加载失败」，看不出根因。
  const list = await casesApi.get('cases').json<components['schemas']['CaseOut'][]>()
  const hit = list.find((c) => c.name === caseName)
  if (hit?.id == null) throw new Error('演示数据创建失败：建完案件后查不到（请刷新重试）')
  const caseId = Number(hit.id)
  const realName = hit.name ?? caseName

  // ④ 兜底补齐案件的关键字段。
  //    `/contracts/contracts/full` 建出来的案件实测 **current_stage 为空**
  //    （只落了 name/case_type/target_amount/parties），而 current_stage 决定
  //    整包分段用哪个模板、起诉条件走哪套校验 —— 空阶段会让二审案按一审校验。
  //    所以这里显式补一次 PUT，不依赖 full 接口把每个字段都透传。
  await ensureCaseFields(caseId, sc)

  // ③ 原告也要挂到案件上 —— 否则一张网立案会判「我方不是原告方」
  if (plaintiffClientId) {
    await addCaseParty(caseId, plaintiffClientId, 'plaintiff')
  }

  return { caseId, contractId, caseName: realName }
}

/**
 * 当前登录律师的 id。
 *
 * 为什么需要：`/contracts/contracts/full` 强制要求 `lawyer_ids` 非空
 * （后端原文「至少需要指派一个律师」），而演示建的是「自己的委托」，
 * 主办律师就是当前用户。
 * 取不到时抛错 —— 用假 id 会建出别人的委托，演示数据就脏了。
 */
async function currentLawyerId(): Promise<number> {
  const orgApi = createApiClient({ prefix: '/api/v1/organization' })
  // 先试 me 端点；没有就从律师列表里按当前用户名匹配
  try {
    const me = await orgApi.get('me').json<{ id?: number }>()
    if (me?.id != null) return Number(me.id)
  } catch {
    /* 端点不存在，走下面的兜底 */
  }
  const uname = readUsername()
  const list = await orgApi
    .get('lawyers')
    .json<{ items?: { id: number; username: string }[] } | { id: number; username: string }[]>()
    .catch(() => [] as { id: number; username: string }[])
  const arr = Array.isArray(list) ? list : (list.items ?? [])
  const hit = arr.find((l) => l.username === uname)
  if (hit) return Number(hit.id)
  throw new Error('无法确定当前律师，演示数据未创建（请重新登录后重试）')
}

/** 从 localStorage 读当前登录用户名（登录时写入） */
function readUsername(): string {
  try {
    return localStorage.getItem('username') ?? ''
  } catch {
    return ''
  }
}

/** 建客户（已存在则复用：后端按名字去重的能力不保证，这里先查后建） */
async function ensureClient(p: {
  name: string
  clientType: string
  isOurClient: boolean
  idNumber: string
  address: string
  legalRep?: string
}): Promise<number | null> {
  try {
    const created = await clientApi
      .post('clients', {
        json: {
          name: p.name,
          client_type: p.clientType,
          is_our_client: p.isOurClient,
          id_number: p.idNumber,
          address: p.address,
          legal_representative: p.legalRep ?? '',
        },
      })
      .json<{ id?: number }>()
    return created?.id != null ? Number(created.id) : null
  } catch {
    // 重名时后端可能拒绝；此时按名字查一次
    try {
      const list = await clientApi
        .get('clients', { searchParams: { search: p.name } })
        .json<{ items?: { id: number; name: string }[] } | { id: number; name: string }[]>()
      const arr = Array.isArray(list) ? list : (list.items ?? [])
      const hit = arr.find((c) => c.name === p.name)
      return hit ? Number(hit.id) : null
    } catch {
      return null
    }
  }
}

/**
 * 确保案件带上 current_stage / cause_of_action 这些「决定后续行为」的字段。
 *
 * 为什么单独一步：full 接口建案时这些字段没有落库（实测 current_stage 为空）。
 * 而 current_stage 是**分段模板与校验规则的分流依据** —— 为空时二审案会按
 * 一审流程走，材料齐备度会去问「催收记录」而不是「答辩状」。
 * 宁可多调一次接口，也不要让演示走到一半才发现阶段丢了。
 */
async function ensureCaseFields(caseId: number, sc: DemoScenario): Promise<void> {
  try {
    await casesApi.put(`cases/${caseId}`, {
      json: {
        name: undefined, // 不改名字（PUT 是全量语义，没给的字段后端会保留）
        current_stage: sc.stage,
        cause_of_action: sc.cause,
        target_amount: sc.targetAmount,
        start_date: today(),
      },
    })
  } catch {
    /* 补字段失败不阻断：页面会显示「阶段未设」，律师一眼能看出 */
  }
}

/** 把客户挂成案件当事人。失败不阻断（页面会如实显示「原告 缺」） */
async function addCaseParty(caseId: number, clientId: number, legalStatus: string): Promise<void> {
  try {
    await casesApi.post('parties', {
      json: { case_id: caseId, client_id: clientId, legal_status: legalStatus },
    })
  } catch {
    /* 已存在或字段不符都不阻断演示 */
  }
}

/** 取演示用整包 PDF：从 public/ 取，不依赖本地文件系统路径 */
export async function fetchDemoPdf(sc: DemoScenario): Promise<File> {
  const res = await fetch(sc.file)
  if (!res.ok) throw new Error(`演示材料加载失败（${res.status}）`)
  const blob = await res.blob()
  const name = decodeURIComponent(sc.file.split('/').pop() ?? '演示材料.pdf')
  return new File([blob], name, { type: 'application/pdf' })
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}
