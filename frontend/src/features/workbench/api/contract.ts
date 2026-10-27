import type {
  CaseListItem,
  ContractListItem,
  ContractPageResponse,
  LawyerListItem,
  ReminderOut,
} from '../types'
import { casesApi, contractsApi, organizationApi, remindersApi } from './client'

/** 分页拉取合同（服务端分页 + facets 全库计数；搜索/筛选随行，排序后端固定 id 倒序） */
export async function listContractsPage(opts: {
  page: number
  pageSize?: number
  status?: string
  cat?: string
  fee?: string
  q?: string
  /** 是否要 facets 计数（默认 true）。翻页时传 false：facets 是全库口径，
   *  与页码无关，逐页重算是 4 次白扫全表。 */
  includeFacets?: boolean
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
        ...(opts.includeFacets === false ? { include_facets: 'false' } : {}),
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
 * 单份合同（详情页直达 /projects/:id 时列表缓存不一定在）。端点返回全量 ContractOut，
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

/**
 * 律师列表：slim=true 只取 id/real_name/phone/license_no/law_firm_name——
 * 本域只做「lawyer_id → 人名/电话/执业证/律所名」映射，不需要文件签 URL
 * 和律所嵌套对象（全量 500 人时那是 1000 次多余签名 + 嵌套 DTO 构建）。
 */
export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers', { searchParams: { slim: 'true' } }).json<LawyerListItem[]>()
}
