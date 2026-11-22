/**
 * 「新建项目」链路的接口层：当前律师 / 空白项目 / 模板项目 / 示例材料上传。
 *
 * **为什么从 `NewProjectDialog` 搬出来**：对话框原先在点击时现建 4 个 ky 实例
 * （cases / contracts / client / inbox）外加 organization，端点路径和默认字段值
 * 直接写在 JSX 旁边——`contracts/full`、`messages/upload`、`me` 这些路径在本域
 * 其它地方一律落在 `api/*.ts` 且有单测，唯独新建项目这条链绕过了接口层。
 * 搬进来以后端点路径、请求体、超时都只在这里出现一份。
 *
 * 建出来的都是**普通项目**（没有任何演示/模板标记）：模板只是把表单字段预先
 * 填好，示例材料走的也是真实上传入口（进收件箱 → 待处理）。
 */

import { UPLOAD_TIMEOUT_MS } from '@/lib/api'

import { DEFAULT_CASE_STAGE, DEFAULT_CASE_TYPE, DEFAULT_FIXED_FEE_AMOUNT } from '../constants'
import { createFromTemplate, fetchSampleFile, type ProjectTemplate } from '../templates'
import { casesApi, clientApi, contractsApi, inboxApi, organizationApi } from './client'

/**
 * 当前律师 id（新建项目必须指派主办律师）。
 *
 * 先问 `organization/me`；该端点不可用时退回律师列表首位——这是老登录态
 * （没有 me 端点）的兜底，两者都拿不到才算真的无法建项目。
 */
export async function currentLawyerId(): Promise<number> {
  try {
    const me = await organizationApi.get('me').json<{ id?: number }>()
    if (me?.id != null) return Number(me.id)
  } catch {
    /* 端点不可用时走兜底 */
  }
  const list = await organizationApi.get('lawyers').json<{ id: number }[] | { items?: { id: number }[] }>()
  const arr = Array.isArray(list) ? list : (list.items ?? [])
  if (arr[0]?.id != null) return Number(arr[0].id)
  throw new Error('无法确定当前律师，请重新登录后重试')
}

/**
 * 建空白项目：一份合同 + 一个初始案件，其余字段律师自己填。
 *
 * 返回两个 id：合同 id 与案件 id 是两套独立自增的主键，跳转时要按视角用对
 * （`/projects/:id` 要合同 id，办案工作台要案件 id），所以在这里显式取回，
 * 不在跳转处猜。
 */
export async function createBlankProject(
  name: string,
  lawyerId: number,
): Promise<{ caseId: number; contractId: number | null }> {
  const contract = await contractsApi
    .post('contracts/full', {
      json: {
        name,
        case_type: DEFAULT_CASE_TYPE,
        status: 'active',
        start_date: new Date().toISOString().slice(0, 10),
        lawyer_ids: [lawyerId],
        fee_mode: 'FIXED',
        fixed_amount: DEFAULT_FIXED_FEE_AMOUNT,
        cases: [
          {
            name: `${name}·案件`,
            case_type: DEFAULT_CASE_TYPE,
            status: 'active',
            current_stage: DEFAULT_CASE_STAGE,
            cause_of_action: '',
          },
        ],
      },
    })
    .json<{ id?: number }>()
  const contractId = contract?.id != null ? Number(contract.id) : null
  // contracts/full 不回案件 id，按合同 id 回查刚建的那个案件
  const list = await casesApi.get('cases').json<{ id?: number; name?: string; contract_id?: number }[]>()
  const hit = list.find((c) => c.contract_id === contract?.id)
  if (hit?.id == null) throw new Error('建项目失败：建完案件后查不到')
  return { caseId: Number(hit.id), contractId }
}

/**
 * 用模板建项目（合同 + 案件 + 当事人 + 管辖法院）。
 *
 * 请求体由 `templates.createFromTemplate` 组装（模板是产品数据，落在这里会
 * 把 200 行的模板表拖进 api 层）；本函数只负责注入本域共用的 ky 实例，
 * 免得调用方自己 new 三个客户端。
 */
export function createProjectFromTemplate(
  template: ProjectTemplate,
  opts: { projectName: string; lawyerId: number },
): Promise<{ contractId: number | null; caseId: number; caseName: string }> {
  return createFromTemplate(template, {
    projectName: opts.projectName,
    lawyerId: opts.lawyerId,
    caseApi: casesApi,
    contractApi: contractsApi,
    clientApi,
  })
}

/**
 * 把模板附带的示例材料放进收件箱（出现在「材料预处理 · 待处理」）。
 *
 * 与真实上传同一条路径、同一个上传超时（大 PDF 走 OCR 前置，慢于普通请求）。
 */
export async function uploadSampleMaterial(template: ProjectTemplate): Promise<void> {
  const file = await fetchSampleFile(template)
  const fd = new FormData()
  fd.append('files', file)
  fd.append('subject', template.sample.label)
  await inboxApi.post('messages/upload', { body: fd, timeout: UPLOAD_TIMEOUT_MS })
}
