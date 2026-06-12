/**
 * 诉讼流程 API
 */
import { createFeatureApiClient } from '@/lib/api'
import type { WorkflowRun, WorkflowDetail, WorkflowTemplate, StepCategory, StepDefinition } from './types'

const client = createFeatureApiClient('workflow')

export const workflowApi = {
  // ── 工作流运行 ──────────────────────────────────────────────────────────────
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

  // ── 模板 CRUD ──────────────────────────────────────────────────────────────
  templates: {
    list: (params?: { category?: string; is_active?: boolean }) =>
      client.get('templates/', { searchParams: params }).json<WorkflowTemplate[]>(),

    get: (id: number) =>
      client.get(`templates/${id}/`).json<WorkflowTemplate>(),

    create: (data: Partial<WorkflowTemplate> & { steps?: unknown[] }) =>
      client.post('templates/', { json: data }).json<{ id: number; name: string; slug: string; message: string }>(),

    update: (id: number, data: Partial<WorkflowTemplate> & { steps?: unknown[] }) =>
      client.put(`templates/${id}/`, { json: data }).json<{ id: number; name: string; message: string }>(),

    delete: (id: number) =>
      client.delete(`templates/${id}/`).json<{ message: string }>(),

    duplicate: (id: number) =>
      client.post(`templates/${id}/duplicate/`).json<{ id: number; name: string; slug: string; message: string }>(),
  },

  // ── 步骤注册表 ─────────────────────────────────────────────────────────────
  stepRegistry: {
    list: () =>
      client.get('step-registry/').json<StepCategory[]>(),

    flat: () =>
      client.get('step-registry/flat/').json<StepDefinition[]>(),
  },
}
