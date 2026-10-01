import { createApiClient } from '@/lib/api'
import type { CaseListItem, ContractListItem, LawyerListItem } from './types'

/**
 * 办案主页数据源：合同 + 律师列表接口只读拉取（slim 模式剔除归档材料清单，
 * 约减 60% 响应体积）；案件按合同 ID 按需加载。
 * 均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const organizationApi = createApiClient({ prefix: '/api/v1/organization' })

export async function listContracts(): Promise<ContractListItem[]> {
  return contractsApi.get('contracts', { searchParams: { slim: 'true' } }).json<ContractListItem[]>()
}

export async function listCasesByContract(contractId: number): Promise<CaseListItem[]> {
  return casesApi
    .get('cases', { searchParams: { contract_id: String(contractId) } })
    .json<CaseListItem[]>()
}

export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers').json<LawyerListItem[]>()
}
