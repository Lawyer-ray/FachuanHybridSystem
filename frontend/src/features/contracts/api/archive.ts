import { createFeatureApiClient } from '@/lib/api'
import { downloadFromResponse } from '@/lib/download'
import type { ArchiveChecklist } from '../types'

const client = createFeatureApiClient('contracts')

export const archiveApi = {
  getChecklist: async (contractId: number | string): Promise<ArchiveChecklist> =>
    client.get(`${contractId}/archive/checklist`).json<ArchiveChecklist>(),

  generateFolder: async (contractId: number | string): Promise<{ success: boolean; generated_docs: string[]; archive_dir: string; errors: string[] }> =>
    client.post(`${contractId}/archive/generate-folder`).json(),

  learnRules: async (): Promise<{ success: boolean; learned: number; updated: number; skipped: number; message: string }> =>
    client.post('archive/learn-rules').json(),

  syncCaseMaterials: async (contractId: number | string): Promise<{ synced_count: number; message: string }> =>
    client.post(`${contractId}/archive/sync-case-materials`).json(),

  resetAndResync: async (contractId: number | string): Promise<{ synced_count: number; message: string }> =>
    client.post(`${contractId}/archive/reset-and-resync`).json(),

  scaleToA4: async (contractId: number | string): Promise<{ scaled_count: number; message: string }> =>
    client.post(`${contractId}/archive/scale-to-a4`).json(),

  toggleCompact: async (contractId: number | string): Promise<{ compact: boolean }> =>
    client.post(`${contractId}/archive/toggle-compact`).json(),

  confirm: async (contractId: number | string): Promise<{ success: boolean; message: string }> =>
    client.post(`${contractId}/archive/confirm`).json(),

  uploadItem: async (contractId: number | string, file: File, category: string): Promise<{ id: number; filename: string }> => {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    return client.post(`${contractId}/archive/upload`, { body: form }).json()
  },

  deleteMaterial: async (contractId: number | string, materialId: number): Promise<void> => {
    await client.delete(`${contractId}/archive/materials/${materialId}`)
  },

  reorderMaterials: async (contractId: number | string, orders: Record<string, number[]>): Promise<void> => {
    await client.post(`${contractId}/archive/reorder`, { json: { orders } })
  },

  moveMaterial: async (contractId: number | string, materialId: number, targetCode: string): Promise<void> => {
    await client.post(`${contractId}/archive/materials/${materialId}/move`, { json: { target_code: targetCode } })
  },

  clearAllMaterials: async (contractId: number | string): Promise<{ deleted_count: number }> =>
    client.post(`${contractId}/archive/clear-all`).json(),

  previewMaterial: async (contractId: number | string, materialId: number): Promise<Response> =>
    client.get(`${contractId}/archive/materials/${materialId}/preview`),

  downloadItem: async (contractId: number | string, archiveItemCode: string): Promise<void> => {
    const resp = await client.get(`${contractId}/archive/download-item/${archiveItemCode}`)
    await downloadFromResponse(resp)
  },

  previewItem: async (contractId: number | string, archiveItemCode: string): Promise<void> => {
    const blob = await client.get(`${contractId}/archive/download-item/${archiveItemCode}?preview=1`).blob()
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  },

  previewSingleMaterial: async (contractId: number | string, materialId: number): Promise<void> => {
    const blob = await client.get(`${contractId}/archive/materials/${materialId}/preview`).blob()
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  },
}
