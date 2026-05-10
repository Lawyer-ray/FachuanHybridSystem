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

export const preservationApi = {
  downloadApplication: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/preservation/application/download`, { json: {} }).blob()
    await downloadBlob(blob, `保全申请书_${caseName ?? caseId}.docx`)
  },

  downloadDelayDelivery: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/preservation/delay-delivery/download`, { json: {} }).blob()
    await downloadBlob(blob, `延迟交货申请_${caseName ?? caseId}.docx`)
  },

  downloadPackage: async (caseId: number | string, caseName?: string) => {
    const blob = client.post(`cases/${caseId}/preservation/package/download`, { json: {} }).blob()
    await downloadBlob(blob, `保全材料包_${caseName ?? caseId}.zip`)
  },
}
