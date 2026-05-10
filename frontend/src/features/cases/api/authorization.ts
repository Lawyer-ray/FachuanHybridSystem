import { createFeatureApiClient } from '@/lib/api'

const client = createFeatureApiClient('documents')

async function downloadBlob(response: Promise<Blob>, filename: string) {
  const blob = await response
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const authorizationApi = {
  downloadPackage: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/authorization/package/download`, { json: {} }).blob()
    await downloadBlob(blob, `授权材料包_${caseName ?? caseId}.zip`)
  },

  downloadLetter: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/authorization/letter/download`, { json: {} }).blob()
    await downloadBlob(blob, `所函_${caseName ?? caseId}.docx`)
  },

  downloadLegalRepCertificate: async (caseId: number | string, clientId: number, clientName?: string) => {
    const blob = client.post(`cases/${caseId}/authorization/legal-rep-certificate/${clientId}/download`, { json: {} }).blob()
    await downloadBlob(blob, `法定代表人证明_${clientName ?? clientId}.docx`)
  },

  downloadPowerOfAttorney: async (caseId: number | string, clientId: number, clientName?: string) => {
    const blob = client.post(`cases/${caseId}/authorization/power-of-attorney/${clientId}/download`, { json: {} }).blob()
    await downloadBlob(blob, `授权委托书_${clientName ?? clientId}.docx`)
  },

  downloadCombinedPOA: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/authorization/power-of-attorney/combined/download`, { json: {} }).blob()
    await downloadBlob(blob, `合并授权委托书_${caseName ?? caseId}.docx`)
  },
}
