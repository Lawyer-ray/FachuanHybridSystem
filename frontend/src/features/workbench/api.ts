import { createApiClient } from '@/lib/api'
import type { CaseListItem, ContractPageResponse, LawyerListItem } from './types'

/**
 * 办案主页数据源：合同 + 律师列表接口只读拉取（slim 模式剔除归档材料清单，
 * 约减 60% 响应体积）；案件按合同 ID 按需加载。
 * 均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const organizationApi = createApiClient({ prefix: '/api/v1/organization' })

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

export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers').json<LawyerListItem[]>()
}
