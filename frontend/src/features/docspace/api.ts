import { createFeatureApiClient } from '@/lib/api'
import type { DocSpaceConfig } from './types'

const api = createFeatureApiClient('docspace')

export const docspaceApi = {
  getConfig: () => api.get('config').json<DocSpaceConfig>(),
}
