/**
 * 诉讼流程类型定义
 */

// ── 工作流运行 ────────────────────────────────────────────────────────────────

export interface WorkflowTemplate {
  id: number
  name: string
  slug: string
  category: 'litigation' | 'preservation' | 'enforcement'
  description: string
  temporal_workflow_name: string
  steps_schema: StepNode[]
  steps_count?: number
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface StepNode {
  id: string
  name: string
  type: StepType
  description?: string
  icon?: string
  mcp_tool?: string
  config?: Record<string, unknown>
  timeout?: string
  retry_max?: number
  on_fail?: string
  signal_key?: string
  condition_field?: string
  condition_operator?: string
  condition_value?: string
  position_x?: number
  position_y?: number
}

export type StepType =
  | 'activity'
  | 'gate'
  | 'wait'
  | 'condition'
  | 'delay'
  | 'llm'
  | 'http'
  | 'code'

// 兼容旧类型
export type StepSchema = StepNode

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

// ── 步骤注册表 ────────────────────────────────────────────────────────────────

export interface StepCategory {
  id: string
  name: string
  icon: string
  steps: StepDefinition[]
}

export interface StepDefinition {
  id: string
  name: string
  type: StepType
  description: string
  icon: string
  mcp_tool?: string
  category_id?: string
  category_name?: string
  config_schema?: Record<string, ConfigField>
}

export interface ConfigField {
  type: 'string' | 'number' | 'textarea' | 'select' | 'boolean'
  required: boolean
  label: string
  placeholder?: string
  help?: string
  default?: unknown
  options?: string[]
}
