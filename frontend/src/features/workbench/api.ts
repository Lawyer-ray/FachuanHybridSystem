import { createApiClient } from '@/lib/api'
import type {
  CaseFolderBindingInfo,
  CaseFolderEntries,
  CaseListItem,
  ContractListItem,
  ContractPageResponse,
  LawyerListItem,
  ReminderOut,
} from './types'

/**
 * 办案主页数据源：合同 + 律师列表接口只读拉取（slim 模式剔除归档材料清单，
 * 约减 60% 响应体积）；案件按合同 ID 按需加载。
 * 均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const organizationApi = createApiClient({ prefix: '/api/v1/organization' })
const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })

/** 分页拉取合同（服务端分页 + facets 全库计数；搜索/筛选随行，排序后端固定「离今天最近」） */
export async function listContractsPage(opts: {
  page: number
  pageSize?: number
  status?: string
  cat?: string
  fee?: string
  q?: string
}): Promise<ContractPageResponse> {
  return contractsApi
    .get('contracts', {
      searchParams: {
        slim: 'true',
        page: String(opts.page),
        page_size: String(opts.pageSize ?? 50),
        ...(opts.status ? { status: opts.status } : {}),
        ...(opts.cat ? { case_type: opts.cat } : {}),
        ...(opts.fee ? { fee_mode: opts.fee } : {}),
        ...(opts.q ? { search: opts.q } : {}),
      },
    })
    .json<ContractPageResponse>()
}

export async function listCasesByContract(contractId: number): Promise<CaseListItem[]> {
  return casesApi
    .get('cases', { searchParams: { contract_id: String(contractId) } })
    .json<CaseListItem[]>()
}

/**
 * 单份合同（详情页直达 /cases/:id 时列表缓存不一定在）。端点返回全量 ContractOut，
 * 本页消费口径与列表行一致（representation_stages 运行时为中文标签数组、id 必有），
 * 多出的 finalized_materials 不消费，按 ContractListItem 投影即可复用 buildDeals。
 */
export async function getContract(contractId: number): Promise<ContractListItem> {
  return contractsApi.get('contracts/' + contractId).json<ContractListItem>()
}

/**
 * 某案件的直挂提醒（开庭等 hearing 类提醒挂在案件上）。/reminders/list 的
 * contract_id / case_id 都是「直挂」口径且互斥，合同直挂随 ContractOut.reminders、
 * 日志级随 CaseOut.logs[].reminders 下发，案件级只能按案逐个取。
 */
export async function listRemindersByCase(caseId: number): Promise<ReminderOut[]> {
  return remindersApi.get('list', { searchParams: { case_id: String(caseId) } }).json<ReminderOut[]>()
}

export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers').json<LawyerListItem[]>()
}

/* ============ 案件绑定文件夹（详情页「文件夹视图」数据源，均只读） ============ */

/** 案件文件夹绑定（未绑定时端点返回 null；404 = 案件不存在/无权） */
export async function getCaseFolderBinding(caseId: number): Promise<CaseFolderBindingInfo | null> {
  return casesApi.get(String(caseId) + '/folder-binding').json<CaseFolderBindingInfo | null>()
}

/** 绑定文件夹某一层子项（subpath 为空 = 根；非递归、不含隐藏项） */
export async function listCaseFolderEntries(caseId: number, subpath: string): Promise<CaseFolderEntries> {
  return casesApi
    .get(String(caseId) + '/folder-entries', { searchParams: subpath ? { subpath } : {} })
    .json<CaseFolderEntries>()
}
