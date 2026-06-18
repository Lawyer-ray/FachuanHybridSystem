import { createFeatureApiClient } from '@/lib/api'
import type { DocSpaceConfig, DocSpaceDocument, DocSpaceUploadResult } from './types'

const api = createFeatureApiClient('docspace')

export const docspaceApi = {
  getConfig: () => api.get('config').json<DocSpaceConfig>(),

  upload: (file: File, folderId?: number) => {
    const form = new FormData()
    form.append('file', file)
    if (folderId != null) form.append('folder_id', String(folderId))
    return api.post('upload', { body: form }).json<DocSpaceUploadResult>()
  },

  createDocument: (title?: string) => {
    const form = new FormData()
    if (title) form.append('title', title)
    return api.post('create', { body: form }).json<DocSpaceUploadResult>()
  },

  listDocuments: () => api.get('documents').json<DocSpaceDocument[]>(),

  getDocument: (id: number) => api.get(`documents/${id}`).json<DocSpaceDocument>(),

  deleteDocument: (id: number) => api.delete(`documents/${id}`).json<{ ok: boolean }>(),

  downloadDocument: (id: number) =>
    api.get(`documents/${id}/download`).blob().then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = ''
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    }),

  syncDocument: (id: number) =>
    api.post(`sync/${id}`).json<DocSpaceDocument>(),
}
