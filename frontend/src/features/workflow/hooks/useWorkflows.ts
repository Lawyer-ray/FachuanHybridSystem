/**
 * 诉讼流程 React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { workflowApi } from '../api'
import type { WorkflowStatus } from '../types'

export function useWorkflows(params?: { case_id?: number; status?: WorkflowStatus }) {
  return useQuery({
    queryKey: ['workflows', params],
    queryFn: () => workflowApi.list(params),
    refetchInterval: (query) => {
      // 有运行中的 workflow 时自动刷新
      const data = query.state.data
      const hasActive = data?.some(
        (r) => r.status === 'running' || r.status === 'waiting_human' || r.status === 'waiting_event'
      )
      return hasActive ? 5000 : false
    },
  })
}

export function useWorkflowDetail(runId: number | null) {
  return useQuery({
    queryKey: ['workflow', runId],
    queryFn: () => workflowApi.detail(runId!),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'waiting_human' ? 5000 : false
    },
  })
}

export function useApproveWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, approved, comment }: { runId: number; approved: boolean; comment?: string }) =>
      workflowApi.approve(runId, approved, comment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      queryClient.invalidateQueries({ queryKey: ['workflow'] })
    },
  })
}

export function useCancelWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: number) => workflowApi.cancel(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: number) => workflowApi.delete(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })
}
