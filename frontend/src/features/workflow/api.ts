/**
 * 诉讼流程 API
 */
import { createFeatureApiClient } from '@/lib/api'
import type { WorkflowRun, WorkflowDetail } from './types'

const client = createFeatureApiClient('workflow')

export const workflowApi = {
  list: (params?: { case_id?: number; status?: string }) =>
    client.get('runs/', { searchParams: params }).json<WorkflowRun[]>(),

  detail: (runId: number) =>
    client.get(`runs/${runId}/`).json<WorkflowDetail>(),

  start: (templateSlug: string, caseId: number) =>
    client.post('start/', { json: { template_slug: templateSlug, case_id: caseId } }).json<{
      run_id: number
      workflow_id: string
      status: string
      message: string
    }>(),

  approve: (runId: number, approved: boolean, comment?: string) =>
    client.post(`runs/${runId}/approve/`, {
      json: { approved, comment: comment || '' },
    }).json<{ message: string }>(),

  cancel: (runId: number) =>
    client.post(`runs/${runId}/cancel/`).json<{ message: string }>(),
}
