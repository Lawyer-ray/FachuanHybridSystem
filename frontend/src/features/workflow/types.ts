/**
 * 诉讼流程类型定义
 */

export interface WorkflowTemplate {
  id: number
  name: string
  slug: string
  category: 'litigation' | 'preservation' | 'enforcement'
  description: string
  temporal_workflow_name: string
  steps_schema: StepSchema[]
  is_active: boolean
}

export interface StepSchema {
  id: string
  name: string
  type: 'activity' | 'gate' | 'wait'
  signal_key?: string
  timeout?: string
  retry_max?: number
  on_fail?: string
}

export type WorkflowStatus =
  | 'running'
  | 'waiting_human'
  | 'waiting_event'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out'

export interface WorkflowRun {
  run_id: number
  workflow_id: string
  template: string
  case_name: string
  status: WorkflowStatus
  current_step: string
  started_at: string
}

export interface StepExecution {
  step_id: string
  name: string
  type: string
  status: 'running' | 'success' | 'failed' | 'waiting' | 'skipped'
  output_summary: string | null
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface WorkflowDetail {
  run_id: number
  template: string
  case_name: string
  status: WorkflowStatus
  current_step: string
  result: Record<string, unknown> | null
  steps: StepExecution[]
  started_at: string
  finished_at: string | null
}
