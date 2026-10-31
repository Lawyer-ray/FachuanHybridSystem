import type { KyInstance } from 'ky'

import type { components } from '@/types/api-schema'

/**
 * 示例项目模板 —— 新建项目时可选「从示例开始」。
 *
 * ═══ 为什么做成模板而不是「演示按钮」═══
 * 最早我在材料预处理页加了个「演示」按钮，一键把案件+材料都建好。
 * 那不成立：它把「新建项目」「上传材料」这两个**产品自己的环节**暗中做掉了，
 * 等于绕过产品。而且带来一堆「演示专用」的复杂度 —— 重置逻辑、[演示] 前缀、
 * 脏数据清理，全是为了维护这个旁路。
 *
 * 做成模板就干净了：
 *   · 它挂在「新建项目」里，是产品正常入口的一个选项（真实产品都有「从模板创建」）
 *   · 建出来的是**普通项目**，没有任何特殊标记，用户后续照常操作
 *   · 材料还是要他自己上传（模板只给「要传哪个文件」的提示 + 一键填入）
 *
 * ═══ 模板给什么 ═══
 * 合同名、案件类型、阶段、当事人、标的额、管辖法院、要上传的示例文件路径。
 * 这些都是「新建项目表单」本来的字段，模板只是替用户填好。
 */

/** 示例材料文件（放在 public/demo-materials/，与真实上传走同一条路径） */
export interface SampleMaterial {
  /** 静态资源路径 */
  file: string
  /** 界面上显示的名字 */
  label: string
  /** 一句话说明这份包是什么 */
  desc: string
  pages: number
  docs: number
}

export interface ProjectTemplate {
  key: string
  title: string
  /** 一句话说明这个模板适合什么场景 */
  summary: string
  /** 案件类型（后端 case_type 枚举） */
  caseType: string
  /** 案件阶段 */
  stage: string
  /** 案由 */
  cause: string
  /** 标的额（字符串，后端 Decimal） */
  targetAmount: string
  /** 管辖法院 */
  court: string
  /** 我方（委托人） */
  our: { name: string; legalRep: string; address: string; idNumber: string }
  /** 对方当事人 */
  their: { name: string; idNumber: string; address: string }[]
  /** 随模板提供的示例材料包 */
  sample: SampleMaterial
}

export const PROJECT_TEMPLATES: ProjectTemplate[] = [
  {
    key: 'mortgage_filing',
    title: '个人住房贷款 · 起诉',
    summary: '银行移交的完整信贷档案（不良监控→贷前尽调→抵押评估→合同→抵登→流水→催收），30 页 12 份材料',
    caseType: 'civil',
    stage: 'first_trial',
    cause: '金融借款合同纠纷',
    targetAmount: '999722.11',
    court: '某某市某某区人民法院',
    our: {
      name: '某某银行股份有限公司某某城南支行',
      legalRep: '陈某某',
      address: '某某大道 200 号某某大厦 1-3 层（虚构）',
      idNumber: '',
    },
    their: [
      { name: '谭某某', idNumber: '110101199305110008', address: '某某路 18 号（虚构）' },
      { name: '梁某某', idNumber: '110101199508050009', address: '某某村 6 组（虚构）' },
    ],
    sample: {
      file: '/demo-materials/银行移交材料包（起诉用·整包扫描件）.pdf',
      label: '银行移交材料包（起诉用）',
      desc: '抵押房贷的完整银行档案，最标准的单笔起诉材料',
      pages: 30,
      docs: 12,
    },
  },
  {
    key: 'consumer_loan_batch',
    title: '消费贷 · 批量诉讼',
    summary: '一份框架协议 + 5 笔提款，每笔「合同→凭证→明细」三件套，27 页 19 份材料',
    caseType: 'civil',
    stage: 'first_trial',
    cause: '金融借款合同纠纷',
    targetAmount: '49263.55',
    court: '某某市某某区人民法院',
    our: {
      name: '某某银行股份有限公司某某分行',
      legalRep: '陈某某',
      address: '某某大道 100 号某某大厦（虚构）',
      idNumber: '',
    },
    their: [{ name: '周某某', idNumber: '110101199007150001', address: '某某镇某某路 8 号（虚构）' }],
    sample: {
      file: '/demo-materials/1-第一次提交证据（整包扫描件）.pdf',
      label: '消费贷批量证据包',
      desc: '消费贷逐笔提款，最能体现批量拆分能力',
      pages: 27,
      docs: 19,
    },
  },
  {
    key: 'appeal_defense',
    title: '二审 · 应诉答辩',
    summary: '法院送达的一审判决书 + 对方上诉状 + 一审庭审笔录，8 页 4 份材料',
    caseType: 'civil',
    stage: 'second_trial',
    cause: '金融借款合同纠纷',
    targetAmount: '437500.00',
    court: '某某市中级人民法院',
    our: {
      name: '某某银行股份有限公司某某城南支行',
      legalRep: '陈某某',
      address: '某某大道 200 号某某大厦 1-3 层（虚构）',
      idNumber: '',
    },
    their: [{ name: '吴某某', idNumber: '110101199101010005', address: '某某街道某某路（虚构）' }],
    sample: {
      file: '/demo-materials/二审收案材料包（整包扫描件）.pdf',
      label: '二审收案材料包',
      desc: '对方上诉后的收案材料，答辩状由律所自己写',
      pages: 8,
      docs: 4,
    },
  },
]

/** 按 key 取模板 */
export function findTemplate(key: string): ProjectTemplate | undefined {
  return PROJECT_TEMPLATES.find((t) => t.key === key)
}

/** 下载示例材料为 File（走 public/ 静态资源，与真实上传同一路径） */
export async function fetchSampleFile(t: ProjectTemplate): Promise<File> {
  const res = await fetch(t.sample.file)
  if (!res.ok) throw new Error(`示例材料加载失败（${res.status}）`)
  const blob = await res.blob()
  const name = decodeURIComponent(t.sample.file.split('/').pop() ?? '示例材料.pdf')
  return new File([blob], name, { type: 'application/pdf' })
}

/**
 * 用模板建项目（合同 + 案件 + 当事人 + 主办律师 + 管辖法院）。
 *
 * 建出来的是**普通项目**：名字不带任何 [演示] 标记，用户后续照常编辑/删除。
 * 模板只是把「新建项目表单」的字段预先填好，不是另一套数据。
 */
export async function createFromTemplate(
  t: ProjectTemplate,
  opts: {
    projectName: string
    lawyerId: number
    caseApi: KyInstance
    contractApi: KyInstance
    clientApi: KyInstance
  },
): Promise<{ contractId: number | null; caseId: number; caseName: string }> {
  const { projectName, lawyerId, caseApi, contractApi, clientApi } = opts

  // ① 委托人（我方）客户档案
  const ourClientId = await ensureClient(clientApi, {
    name: t.our.name,
    clientType: 'legal',
    isOur: true,
    idNumber: t.our.idNumber,
    address: t.our.address,
    legalRep: t.our.legalRep,
  })

  // ② 对方当事人
  const theirIds: number[] = []
  for (const p of t.their) {
    const id = await ensureClient(clientApi, {
      name: p.name,
      clientType: 'natural',
      isOur: false,
      idNumber: p.idNumber,
      address: p.address,
    })
    if (id) theirIds.push(id)
  }

  // ③ 合同（委托关系）
  let contractId: number | null = null
  try {
    const c = await contractApi
      .post('contracts/full', {
        json: {
          name: `${projectName}·委托合同`,
          case_type: t.caseType,
          status: 'active',
          start_date: today(),
          representation_stages: [t.stage],
          lawyer_ids: [lawyerId],
          fee_mode: 'FIXED',
          fixed_amount: 5000,
          parties: ourClientId ? [{ client_id: ourClientId, role: 'PRINCIPAL' }] : [],
          cases: [],
        },
      })
      .json<{ id?: number }>()
    contractId = c?.id != null ? Number(c.id) : null
  } catch {
    // 合同建失败不阻断：案件可以独立存在，只是 OA 立案用不了
  }

  // ④ 案件（一次建齐 案件+当事人+指派+管辖法院）
  const caseName = `${projectName}·${t.their.map((x) => x.name).join('、')}${t.cause}`
  const created = await caseApi
    .post('cases/full', {
      json: {
        case: {
          name: caseName,
          case_type: t.caseType,
          status: 'active',
          current_stage: t.stage,
          cause_of_action: t.cause,
          target_amount: t.targetAmount,
        },
        parties: [
          ...(ourClientId ? [{ client_id: ourClientId, legal_status: 'plaintiff' }] : []),
          ...theirIds.map((id) => ({ client_id: id, legal_status: 'defendant' })),
        ],
        assignments: [{ lawyer_id: lawyerId }],
        supervising_authorities: [{ name: t.court, authority_type: 'trial' }],
        logs: [],
        case_numbers: [],
      },
    })
    .json<components['schemas']['CaseOut']>()

  const caseId = Number(created?.id)
  if (!Number.isFinite(caseId)) throw new Error('建项目失败：后端未返回案件 id')
  return { contractId, caseId, caseName: created?.name ?? caseName }
}

/** 建客户；重名/证件号冲突时按名字回查 */
async function ensureClient(
  api: KyInstance,
  p: {
    name: string
    clientType: string
    isOur: boolean
    idNumber: string
    address: string
    legalRep?: string
  },
): Promise<number | null> {
  try {
    const r = await api
      .post('clients', {
        json: {
          name: p.name,
          client_type: p.clientType,
          is_our_client: p.isOur,
          id_number: p.idNumber,
          address: p.address,
          legal_representative: p.legalRep ?? '',
        },
      })
      .json<{ id?: number }>()
    return r?.id != null ? Number(r.id) : null
  } catch {
    return null
  }
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}
