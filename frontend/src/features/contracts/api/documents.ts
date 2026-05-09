import { api } from '@/lib/api'

export const documentsApi = {
  previewArchivePlaceholders: async (contractId: number | string, templateSubtype: string): Promise<{ success: boolean; data?: { key: string; label: string; value: string }[]; error?: string }> =>
    api.get(`documents/contracts/${contractId}/archive-preview`, { searchParams: { template_subtype: templateSubtype } }).json(),

  generateContract: async (contractId: number | string, splitFee = false): Promise<Response> =>
    api.get(`documents/contracts/${contractId}/download`, { searchParams: splitFee ? { split_fee: 'true' } : {} }),

  generateFolder: async (contractId: number | string): Promise<Blob> =>
    api.get(`documents/contracts/${contractId}/folder/download`).blob(),

  generateSupplementaryAgreement: async (contractId: number | string, agreementId: number): Promise<Response> =>
    api.get(`documents/contracts/${contractId}/supplementary-agreements/${agreementId}/download`),
}
