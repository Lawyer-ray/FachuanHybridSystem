import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { TemplateBindingsResponse, AvailableTemplate } from '../types'

export function useTemplateBindings(caseId: number | string | undefined) {
  return useQuery<TemplateBindingsResponse>({
    queryKey: ['cases', caseId, 'template-bindings'],
    queryFn: () => caseApi.getTemplateBindings(caseId!),
    enabled: !!caseId,
  })
}

export function useAvailableTemplates(caseId: number | string | undefined) {
  return useQuery<AvailableTemplate[]>({
    queryKey: ['cases', caseId, 'available-templates'],
    queryFn: () => caseApi.getAvailableTemplates(caseId!),
    enabled: !!caseId,
  })
}

export default useTemplateBindings
