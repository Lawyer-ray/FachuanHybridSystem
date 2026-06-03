import { createFeatureApiClient } from '@/lib/api'
import type {
  MaterialBindCandidate, MaterialBindItem, MaterialCategory,
  MaterialDeleteAllResponse, MaterialDeleteResponse,
  MaterialGroupRenameResponse, MaterialReplaceResponse, MaterialUploadResponse,
  AvailableTemplate, GenerateTemplateRequest, UnifiedGenerateRequest,
  TemplateBinding, TemplateBindingsResponse,
  FolderBinding, FolderBrowseResponse, FolderScanCandidate, FolderScanSession,
} from '../types'

const client = createFeatureApiClient('cases')

export const materialsApi = {
  listCandidates: async (caseId: number | string): Promise<MaterialBindCandidate[]> =>
    client.get(`${caseId}/materials/bind-candidates`).json<MaterialBindCandidate[]>(),

  bind: async (caseId: number | string, items: MaterialBindItem[]): Promise<{ saved_count: number }> =>
    client.post(`${caseId}/materials/bind`, { json: { items } }).json<{ saved_count: number }>(),

  upload: async (caseId: number | string, files: File[]): Promise<MaterialUploadResponse> => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return client.post(`${caseId}/materials/upload`, { body: formData }).json<MaterialUploadResponse>()
  },

  replace: async (caseId: number | string, materialId: number | string, newAttachmentId: number): Promise<MaterialReplaceResponse> =>
    client.post(`${caseId}/materials/${materialId}/replace`, { json: { new_attachment_id: newAttachmentId } }).json<MaterialReplaceResponse>(),

  renameGroup: async (caseId: number | string, typeId: number, newTypeName: string, updateGlobal = false): Promise<MaterialGroupRenameResponse> =>
    client.post(`${caseId}/materials/group-rename`, { json: { type_id: typeId, new_type_name: newTypeName, update_global: updateGlobal } }).json<MaterialGroupRenameResponse>(),

  delete: async (caseId: number | string, materialId: number | string): Promise<MaterialDeleteResponse> =>
    client.delete(`${caseId}/materials/${materialId}`).json<MaterialDeleteResponse>(),

  deleteAll: async (caseId: number | string, category: MaterialCategory): Promise<MaterialDeleteAllResponse> =>
    client.delete(`${caseId}/materials`, { json: { category } }).json<MaterialDeleteAllResponse>(),

  saveGroupOrder: async (caseId: number | string, category: string, orderedTypeIds: number[], side?: string, supervisingAuthorityId?: number): Promise<{ ok: boolean }> =>
    client.post(`${caseId}/materials/group-order`, {
      json: { category, ordered_type_ids: orderedTypeIds, side, supervising_authority_id: supervisingAuthorityId },
    }).json<{ ok: boolean }>(),

  getTemplateBindings: async (caseId: number | string): Promise<TemplateBindingsResponse> =>
    client.get(`${caseId}/template-bindings`).json<TemplateBindingsResponse>(),

  bindTemplate: async (caseId: number | string, templateId: number): Promise<TemplateBinding> =>
    client.post(`${caseId}/template-bindings`, { json: { template_id: templateId } }).json<TemplateBinding>(),

  unbindTemplate: async (caseId: number | string, bindingId: number | string): Promise<{ success: boolean }> =>
    client.delete(`${caseId}/template-bindings/${bindingId}`).json<{ success: boolean }>(),

  getAvailableTemplates: async (caseId: number | string): Promise<AvailableTemplate[]> =>
    client.get(`${caseId}/available-templates`).json<AvailableTemplate[]>(),

  generateTemplate: async (caseId: number | string, data: GenerateTemplateRequest): Promise<Blob> =>
    client.post(`${caseId}/generate-template`, { json: data }).blob(),

  unifiedGenerate: async (caseId: number | string, data: UnifiedGenerateRequest): Promise<Blob> =>
    client.post(`${caseId}/unified-generate`, { json: data }).blob(),

  getFolderBinding: async (caseId: number | string): Promise<FolderBinding | null> => {
    try {
      return await client.get(`${caseId}/folder-binding`).json<FolderBinding>()
    } catch {
      return null
    }
  },

  createFolderBinding: async (
    caseId: number | string,
    params: { folder_path: string; storage_type?: string; storage_account_id?: number | null },
  ): Promise<FolderBinding> =>
    client.post(`${caseId}/folder-binding`, { json: params }).json<FolderBinding>(),

  deleteFolderBinding: async (caseId: number | string): Promise<void> => {
    await client.delete(`${caseId}/folder-binding`)
  },

  browseFolders: async (path?: string): Promise<FolderBrowseResponse> => {
    const searchParams = new URLSearchParams()
    if (path) searchParams.set('path', path)
    return client.get('folder-browse', { searchParams }).json<FolderBrowseResponse>()
  },

  startFolderScan: async (caseId: number | string, options?: Record<string, unknown>): Promise<FolderScanSession> =>
    client.post(`${caseId}/folder-scan`, { json: options ?? {} }).json<FolderScanSession>(),

  getScanStatus: async (caseId: number | string, sessionId: string): Promise<FolderScanSession> =>
    client.get(`${caseId}/folder-scan/${sessionId}`).json<FolderScanSession>(),

  stageScanResults: async (caseId: number | string, sessionId: string, items: FolderScanCandidate[]): Promise<{ staged_count: number }> =>
    client.post(`${caseId}/folder-scan/${sessionId}/stage`, { json: { items } }).json<{ staged_count: number }>(),
}
