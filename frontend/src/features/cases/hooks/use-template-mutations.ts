import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { GenerateTemplateRequest, UnifiedGenerateRequest } from '../types'
import { caseQueryKey } from './use-case'

export function useTemplateMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
    queryClient.invalidateQueries({ queryKey: ['cases', caseId, 'template-bindings'] })
    queryClient.invalidateQueries({ queryKey: ['cases', caseId, 'available-templates'] })
  }

  const bindTemplate = useMutation({
    mutationFn: (templateId: number) => caseApi.bindTemplate(caseId, templateId),
    onSuccess: invalidateCase,
  })

  const unbindTemplate = useMutation({
    mutationFn: (bindingId: number | string) => caseApi.unbindTemplate(caseId, bindingId),
    onSuccess: invalidateCase,
  })

  const generateTemplate = useMutation({
    mutationFn: (data: GenerateTemplateRequest) => caseApi.generateTemplate(caseId, data),
  })

  const unifiedGenerate = useMutation({
    mutationFn: (data: UnifiedGenerateRequest) => caseApi.unifiedGenerate(caseId, data),
  })

  return { bindTemplate, unbindTemplate, generateTemplate, unifiedGenerate }
}

export default useTemplateMutations
