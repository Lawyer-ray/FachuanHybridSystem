import { createApiClient } from '@/lib/api'
import type { CaseListItem, ContractListItem, LawyerListItem } from './types'

/**
 * 办案主页数据源：合同 + 案件 + 律师三个只读列表接口。
 * 均返回裸数组、无业务 success 包装（见 types.ts 头注释的契约说明）。
 */
const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })
const casesApi = createApiClient({ prefix: '/api/v1/cases' })
const organizationApi = createApiClient({ prefix: '/api/v1/organization' })

export async function listContracts(): Promise<ContractListItem[]> {
  return contractsApi.get('contracts').json<ContractListItem[]>()
}

export async function listCases(): Promise<CaseListItem[]> {
  return casesApi.get('cases').json<CaseListItem[]>()
}

export async function listLawyers(): Promise<LawyerListItem[]> {
  return organizationApi.get('lawyers').json<LawyerListItem[]>()
}
