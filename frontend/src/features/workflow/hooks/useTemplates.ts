/**
 * 工作流模板 React Query Hooks
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workflowApi } from '../api'
import type { WorkflowTemplate } from '../types'

const TEMPLATE_KEYS = {
  all: ['workflow', 'templates'] as const,
  list: (params?: { category?: string; is_active?: boolean }) =>
    [...TEMPLATE_KEYS.all, 'list', params] as const,
  detail: (id: number) => [...TEMPLATE_KEYS.all, 'detail', id] as const,
  registry: ['workflow', 'step-registry'] as const,
}

/** 模板列表 */
export function useTemplates(params?: { category?: string; is_active?: boolean }) {
  return useQuery({
    queryKey: TEMPLATE_KEYS.list(params),
    queryFn: () => workflowApi.templates.list(params),
  })
}

/** 模板详情 */
export function useTemplate(id: number | null) {
  return useQuery({
    queryKey: TEMPLATE_KEYS.detail(id!),
    queryFn: () => workflowApi.templates.get(id!),
    enabled: id !== null,
  })
}

/** 创建模板 */
export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<WorkflowTemplate> & { steps?: unknown[] }) =>
      workflowApi.templates.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATE_KEYS.all }),
  })
}

/** 更新模板 */
export function useUpdateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<WorkflowTemplate> & { steps?: unknown[] } }) =>
      workflowApi.templates.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATE_KEYS.all }),
  })
}

/** 删除模板 */
export function useDeleteTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => workflowApi.templates.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATE_KEYS.all }),
  })
}

/** 复制模板 */
export function useDuplicateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => workflowApi.templates.duplicate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATE_KEYS.all }),
  })
}

/** 步骤注册表 */
export function useStepRegistry() {
  return useQuery({
    queryKey: TEMPLATE_KEYS.registry,
    queryFn: () => workflowApi.stepRegistry.list(),
    staleTime: 5 * 60 * 1000, // 5 分钟内不重新请求
  })
}
