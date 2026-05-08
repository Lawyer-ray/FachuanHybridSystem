import { createFeatureApiClient } from '@/lib/api'

const api = createFeatureApiClient('documents')

export const templateApi = {
  list: () => api.get('templates').json(),
  get: (id: number) => api.get(`templates/${id}`).json(),
  create: (data: unknown) => api.post('templates', { json: data }).json(),
  update: (id: number, data: unknown) => api.put(`templates/${id}`, { json: data }).json(),
  delete: (id: number) => api.delete(`templates/${id}`),
}
