/**
 * Case Feature API
 * 案件管理模块 API 封装
 */

import { createApiClient } from '@/lib/api'

import type {
  AvailableTemplate,
  Case,
  CaseAccessGrant,
  CaseAssignment,
  CaseCreateFull,
  CaseInput,
  CaseListParams,
  CaseLog,
  CaseLogAttachment,
  CaseNumber,
  CaseParty,
  CaseUpdate,
  CauseItem,
  CauseTreeNode,
  CourtItem,
  FeeCalculationRequest,
  FeeCalculationResponse,
  FolderBinding,
  FolderBrowseResponse,
  FolderScanCandidate,
  FolderScanSession,
  GenerateTemplateRequest,
  MaterialBindCandidate,
  MaterialBindItem,
  MaterialCategory,
  MaterialDeleteAllResponse,
  MaterialDeleteResponse,
  MaterialGroupRenameResponse,
  MaterialReplaceResponse,
  MaterialUploadResponse,
  SupervisingAuthority,
  TemplateBinding,
  TemplateBindingsResponse,
  UnifiedGenerateRequest,
} from './types'

const api = createApiClient({ prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/cases` })

/** CaseFullOut response from POST /cases/full */
interface CaseFullOut {
  case: Case
  parties: CaseParty[]
  assignments: CaseAssignment[]
  logs: CaseLog[]
  case_numbers: CaseNumber[]
  supervising_authorities: SupervisingAuthority[]
}

export const caseApi = {
  // ==================== 案件 CRUD ====================

  list: async (params?: CaseListParams): Promise<Case[]> => {
    const searchParams = new URLSearchParams()
    if (params?.case_type) searchParams.set('case_type', params.case_type)
    if (params?.status) searchParams.set('status', params.status)
    if (params?.case_number) searchParams.set('case_number', params.case_number)
    return api.get('cases', { searchParams }).json<Case[]>()
  },

  search: async (q: string, limit = 10): Promise<Case[]> => {
    return api.get('cases/search', { searchParams: { q, limit: String(limit) } }).json<Case[]>()
  },

  get: async (id: number | string): Promise<Case> => {
    return api.get(`cases/${id}`).json<Case>()
  },

  create: async (data: CaseInput): Promise<Case> => {
    return api.post('cases', { json: data }).json<Case>()
  },

  createFull: async (data: CaseCreateFull): Promise<CaseFullOut> => {
    return api.post('cases/full', { json: data }).json<CaseFullOut>()
  },

  update: async (id: number | string, data: CaseUpdate): Promise<Case> => {
    return api.put(`cases/${id}`, { json: data }).json<Case>()
  },

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`cases/${id}`)
  },

  // ==================== 当事人 ====================

  listParties: async (caseId: number | string): Promise<CaseParty[]> => {
    return api.get('parties', { searchParams: { case_id: String(caseId) } }).json<CaseParty[]>()
  },

  createParty: async (data: { case_id: number; client_id: number; legal_status?: string }): Promise<CaseParty> => {
    return api.post('parties', { json: data }).json<CaseParty>()
  },

  updateParty: async (id: number | string, data: { case_id?: number; client_id?: number; legal_status?: string }): Promise<CaseParty> => {
    return api.put(`parties/${id}`, { json: data }).json<CaseParty>()
  },

  deleteParty: async (id: number | string): Promise<void> => {
    await api.delete(`parties/${id}`)
  },

  // ==================== 指派 ====================

  listAssignments: async (caseId: number | string): Promise<CaseAssignment[]> => {
    return api.get('assignments', { searchParams: { case_id: String(caseId) } }).json<CaseAssignment[]>()
  },

  createAssignment: async (data: { case_id: number; lawyer_id: number }): Promise<CaseAssignment> => {
    return api.post('assignments', { json: data }).json<CaseAssignment>()
  },

  deleteAssignment: async (id: number | string): Promise<void> => {
    await api.delete(`assignments/${id}`)
  },

  // ==================== 授权访问 ====================

  listGrants: async (caseId: number | string): Promise<CaseAccessGrant[]> => {
    return api.get('grants', { searchParams: { case_id: String(caseId) } }).json<CaseAccessGrant[]>()
  },

  createGrant: async (data: { case_id: number; grantee_id: number }): Promise<CaseAccessGrant> => {
    return api.post('grants', { json: data }).json<CaseAccessGrant>()
  },

  deleteGrant: async (id: number | string): Promise<void> => {
    await api.delete(`grants/${id}`)
  },

  // ==================== 日志 ====================

  listLogs: async (caseId: number | string): Promise<CaseLog[]> => {
    return api.get('logs', { searchParams: { case_id: String(caseId) } }).json<CaseLog[]>()
  },

  createLog: async (data: { case_id: number; content: string; reminder_type?: string; reminder_time?: string }): Promise<CaseLog> => {
    return api.post('logs', { json: data }).json<CaseLog>()
  },

  updateLog: async (id: number | string, data: { case_id?: number; content?: string }): Promise<CaseLog> => {
    return api.put(`logs/${id}`, { json: data }).json<CaseLog>()
  },

  deleteLog: async (id: number | string): Promise<void> => {
    await api.delete(`logs/${id}`)
  },

  uploadLogAttachments: async (logId: number | string, files: File[]): Promise<CaseLogAttachment[]> => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return api.post(`logs/${logId}/attachments`, { body: formData }).json<CaseLogAttachment[]>()
  },

  // ==================== 案号 ====================

  listCaseNumbers: async (caseId: number | string): Promise<CaseNumber[]> => {
    return api.get('case-numbers', { searchParams: { case_id: String(caseId) } }).json<CaseNumber[]>()
  },

  createCaseNumber: async (data: { case_id: number; number: string; remarks?: string; document_name?: string; is_active?: boolean; execution_cutoff_date?: string | null; execution_paid_amount?: number; execution_use_deduction_order?: boolean; execution_year_days?: number | null; execution_date_inclusion?: string | null; execution_manual_text?: string | null }): Promise<CaseNumber> => {
    return api.post('case-numbers', { json: data }).json<CaseNumber>()
  },

  updateCaseNumber: async (id: number | string, data: { number?: string; remarks?: string; document_name?: string; is_active?: boolean; execution_cutoff_date?: string | null; execution_paid_amount?: number; execution_use_deduction_order?: boolean; execution_year_days?: number | null; execution_date_inclusion?: string | null; execution_manual_text?: string | null }): Promise<CaseNumber> => {
    return api.put(`case-numbers/${id}`, { json: data }).json<CaseNumber>()
  },

  deleteCaseNumber: async (id: number | string): Promise<void> => {
    await api.delete(`case-numbers/${id}`)
  },

  // ==================== 材料管理 ====================

  listMaterialCandidates: async (caseId: number | string): Promise<MaterialBindCandidate[]> => {
    return api.get(`${caseId}/materials/bind-candidates`).json<MaterialBindCandidate[]>()
  },

  bindMaterials: async (caseId: number | string, items: MaterialBindItem[]): Promise<{ saved_count: number }> => {
    return api.post(`${caseId}/materials/bind`, { json: { items } }).json<{ saved_count: number }>()
  },

  uploadMaterials: async (caseId: number | string, files: File[]): Promise<MaterialUploadResponse> => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return api.post(`${caseId}/materials/upload`, { body: formData }).json<MaterialUploadResponse>()
  },

  replaceMaterial: async (caseId: number | string, materialId: number | string, newAttachmentId: number): Promise<MaterialReplaceResponse> => {
    return api.post(`${caseId}/materials/${materialId}/replace`, { json: { new_attachment_id: newAttachmentId } }).json<MaterialReplaceResponse>()
  },

  renameMaterialGroup: async (caseId: number | string, typeId: number, newTypeName: string, updateGlobal = false): Promise<MaterialGroupRenameResponse> => {
    return api.post(`${caseId}/materials/group-rename`, { json: { type_id: typeId, new_type_name: newTypeName, update_global: updateGlobal } }).json<MaterialGroupRenameResponse>()
  },

  deleteMaterial: async (caseId: number | string, materialId: number | string): Promise<MaterialDeleteResponse> => {
    return api.delete(`${caseId}/materials/${materialId}`).json<MaterialDeleteResponse>()
  },

  deleteAllMaterials: async (caseId: number | string, category: MaterialCategory): Promise<MaterialDeleteAllResponse> => {
    return api.delete(`${caseId}/materials`, { json: { category } }).json<MaterialDeleteAllResponse>()
  },

  saveMaterialGroupOrder: async (caseId: number | string, category: string, orderedTypeIds: number[], side?: string, supervisingAuthorityId?: number): Promise<{ ok: boolean }> => {
    return api.post(`${caseId}/materials/group-order`, {
      json: { category, ordered_type_ids: orderedTypeIds, side, supervising_authority_id: supervisingAuthorityId },
    }).json<{ ok: boolean }>()
  },

  // ==================== 模板绑定 ====================

  getTemplateBindings: async (caseId: number | string): Promise<TemplateBindingsResponse> => {
    return api.get(`${caseId}/template-bindings`).json<TemplateBindingsResponse>()
  },

  bindTemplate: async (caseId: number | string, templateId: number): Promise<TemplateBinding> => {
    return api.post(`${caseId}/template-bindings`, { json: { template_id: templateId } }).json<TemplateBinding>()
  },

  unbindTemplate: async (caseId: number | string, bindingId: number | string): Promise<{ success: boolean }> => {
    return api.delete(`${caseId}/template-bindings/${bindingId}`).json<{ success: boolean }>()
  },

  getAvailableTemplates: async (caseId: number | string): Promise<AvailableTemplate[]> => {
    return api.get(`${caseId}/available-templates`).json<AvailableTemplate[]>()
  },

  generateTemplate: async (caseId: number | string, data: GenerateTemplateRequest): Promise<Blob> => {
    return api.post(`${caseId}/generate-template`, { json: data }).blob()
  },

  unifiedGenerate: async (caseId: number | string, data: UnifiedGenerateRequest): Promise<Blob> => {
    return api.post(`${caseId}/unified-generate`, { json: data }).blob()
  },

  // ==================== 文件夹绑定 ====================

  getFolderBinding: async (caseId: number | string): Promise<FolderBinding | null> => {
    try {
      return await api.get(`${caseId}/folder-binding`).json<FolderBinding>()
    } catch {
      return null
    }
  },

  createFolderBinding: async (caseId: number | string, folderPath: string): Promise<FolderBinding> => {
    return api.post(`${caseId}/folder-binding`, { json: { folder_path: folderPath } }).json<FolderBinding>()
  },

  deleteFolderBinding: async (caseId: number | string): Promise<void> => {
    await api.delete(`${caseId}/folder-binding`)
  },

  browseFolders: async (path?: string): Promise<FolderBrowseResponse> => {
    const searchParams = new URLSearchParams()
    if (path) searchParams.set('path', path)
    return api.get('folder-browse', { searchParams }).json<FolderBrowseResponse>()
  },

  startFolderScan: async (caseId: number | string, options?: Record<string, unknown>): Promise<FolderScanSession> => {
    return api.post(`${caseId}/folder-scan`, { json: options ?? {} }).json<FolderScanSession>()
  },

  getScanStatus: async (caseId: number | string, sessionId: string): Promise<FolderScanSession> => {
    return api.get(`${caseId}/folder-scan/${sessionId}`).json<FolderScanSession>()
  },

  stageScanResults: async (caseId: number | string, sessionId: string, items: FolderScanCandidate[]): Promise<{ staged_count: number }> => {
    return api.post(`${caseId}/folder-scan/${sessionId}/stage`, { json: { items } }).json<{ staged_count: number }>()
  },

  // ==================== 参考数据 ====================

  searchCauses: async (search: string, caseType?: string, limit = 50): Promise<CauseItem[]> => {
    const searchParams = new URLSearchParams({ search, limit: String(limit) })
    if (caseType) searchParams.set('case_type', caseType)
    return api.get('causes-data', { searchParams }).json<CauseItem[]>()
  },

  getCausesTree: async (parentId?: number): Promise<CauseTreeNode[]> => {
    const searchParams = new URLSearchParams()
    if (parentId !== undefined) searchParams.set('parent_id', String(parentId))
    return api.get('causes-tree', { searchParams }).json<CauseTreeNode[]>()
  },

  searchCourts: async (search: string, limit = 50): Promise<CourtItem[]> => {
    return api.get('courts-data', { searchParams: { search, limit: String(limit) } }).json<CourtItem[]>()
  },

  // ==================== 诉讼费计算 ====================

  calculateFee: async (data: FeeCalculationRequest): Promise<FeeCalculationResponse> => {
    return api.post('calculate-fee', { json: data }).json<FeeCalculationResponse>()
  },
}

export default caseApi
