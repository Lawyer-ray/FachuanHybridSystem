import { createApiClient } from '@/lib/api'

import type { ContractListItem } from '../types'
import { contractsApi, contractFolderApi } from './client'

/**
 * 项目页「办理」里的四个动作（一张网立案 / 申请担保 / OA 立案 / 归档）的接口层。
 *
 * 三条共同形状（照后端实现，不要"优化"）：
 * 1. **先读 `case-info` 再动手**：法院账号有没有、目录齐不齐、OA 凭证配没配，
 *    都在这两个只读端点里。缺凭证时点下去必失败，不如按钮之前就说清。
 * 2. **执行是异步会话**：`execute` 返回 `session_id` + 当前 `status`，之后靠
 *    `session/{id}` 轮询。真实跑一次要开浏览器、填表单、传附件，几十秒到几分钟。
 * 3. **失败必须把后端原话给律师看**：页面改版、验证码、法院退回，只有后端
 *    `message` / `error_message` 说得清，前端不做二次翻译。
 */

const courtFilingApi = createApiClient({ prefix: '/api/v1/court-filing' })
const courtGuaranteeApi = createApiClient({ prefix: '/api/v1/court-guarantee' })
const oaFilingApi = createApiClient({ prefix: '/api/v1/oa-filing' })

/** 一张网立案的就绪信息（`GET /court-filing/case-info/{id}`） */
export interface FilingInfo {
  case_id: number
  case_name: string
  court_name: string | null
  cause_of_action: string | null
  target_amount: string | null
  our_party_is_plaintiff_side: boolean
  /** 法院账号（一张网）是否已配置；false 时按钮必须禁用 */
  has_court_credential: boolean
  /** 法院端 HTTP 插件是否可用（可用则走 api 引擎，否则浏览器自动化） */
  has_http_plugin: boolean
  plugin_available: boolean
  suggested_filing_type: string | null
  default_filing_engine: string | null
}

export interface GuaranteeInfo {
  case_id: number
  case_name: string
  court_name: string | null
  cause_of_action: string | null
  preserve_amount: string | null
  preserve_category: string | null
  /** 还没有案号 = 只能做诉前保全 */
  has_case_number: boolean
  has_court_credential: boolean
  our_party_is_plaintiff_side: boolean
  insurance_company_name: string | null
  insurance_company_options: string[]
}

/** 异步会话的即时回执（立案 / 担保共用） */
export interface CourtSessionOut {
  success: boolean
  message: string
  session_id: number | null
  status: string | null
  timing?: Record<string, unknown> | null
}

export async function getFilingInfo(caseId: number): Promise<FilingInfo> {
  return courtFilingApi.get(`case-info/${caseId}`).json<FilingInfo>()
}

export async function startFiling(input: {
  caseId: number
  filingType?: string | null
  filingEngine?: string | null
}): Promise<CourtSessionOut> {
  return courtFilingApi
    .post('execute', {
      json: {
        case_id: input.caseId,
        ...(input.filingType ? { filing_type: input.filingType } : {}),
        ...(input.filingEngine ? { filing_engine: input.filingEngine } : {}),
      },
    })
    .json<CourtSessionOut>()
}

export async function getFilingSession(sessionId: number): Promise<CourtSessionOut> {
  return courtFilingApi.get(`session/${sessionId}`).json<CourtSessionOut>()
}

export async function getGuaranteeInfo(caseId: number): Promise<GuaranteeInfo> {
  return courtGuaranteeApi.get(`case-info/${caseId}`).json<GuaranteeInfo>()
}

export async function startGuarantee(input: {
  caseId: number
  insuranceCompanyName?: string | null
}): Promise<CourtSessionOut> {
  return courtGuaranteeApi
    .post('execute', {
      json: {
        case_id: input.caseId,
        ...(input.insuranceCompanyName ? { insurance_company_name: input.insuranceCompanyName } : {}),
      },
    })
    .json<CourtSessionOut>()
}

export async function getGuaranteeSession(sessionId: number): Promise<CourtSessionOut> {
  return courtGuaranteeApi.get(`session/${sessionId}`).json<CourtSessionOut>()
}

/** OA 配置（`GET /oa-filing/configs`）：每个 OA 系统一条，含凭证是否配好 */
export interface OaFilingConfig {
  id: string
  oa_system_name: string
  has_credential: boolean
}

export interface OaFilingSessionOut {
  id: number
  status: string
  error_message: string
  created_at: string
}

export async function listOaFilingConfigs(): Promise<OaFilingConfig[]> {
  return oaFilingApi.get('configs').json<OaFilingConfig[]>()
}

/**
 * 提交 OA 立案。
 *
 * 注意它是**合同级**的（`contract_id` 必填，`case_id` 可选）：律所 OA 那边的案件
 * 是按委托立的，不按审级——所以这一项在「办理」里也标成项目级，别让人以为是只立一审。
 */
export async function startOaFiling(input: {
  siteName: string
  contractId: number
  caseId?: number | null
}): Promise<OaFilingSessionOut> {
  return oaFilingApi
    .post('execute', {
      json: {
        site_name: input.siteName,
        contract_id: input.contractId,
        ...(input.caseId != null ? { case_id: input.caseId } : {}),
      },
    })
    .json<OaFilingSessionOut>()
}

export async function getOaFilingSession(sessionId: number): Promise<OaFilingSessionOut> {
  return oaFilingApi.get(`session/${sessionId}`).json<OaFilingSessionOut>()
}

/** 案卷归档清单（`GET /contracts/{id}/archive/checklist`） */
export interface ArchiveChecklistItem {
  code: string
  name: string
  required: boolean
  completed: boolean
}

export interface ArchiveChecklist {
  archive_category: string
  archive_category_label: string
  compact_archive: boolean
  items: ArchiveChecklistItem[]
}

export async function getArchiveChecklist(contractId: number): Promise<ArchiveChecklist> {
  // 归档端点挂在 `/{contract_id}/…`（与文件夹同前缀），**不是** CRUD 的
  // `/contracts/{id}`；用错客户端会拿到 404（实测：用 contractsApi 拼出
  // `/contracts/contracts/448/archive/checklist`）。
  return contractFolderApi.get(`${contractId}/archive/checklist`).json<ArchiveChecklist>()
}

/**
 * 归档 = 把项目状态改成「已归档」。
 *
 * 后端副作用要写在按钮旁边：**该项目下所有在办案件会被一并结案，且改回「在办」
 * 不会自动重开**。走合同更新端点（`payload` 包一层、exclude_unset 只改 status）。
 */
export async function archiveContract(contractId: number): Promise<ContractListItem> {
  return contractsApi
    .put(`contracts/${contractId}`, { json: { payload: { status: 'archived' } } })
    .json<ContractListItem>()
}
