/**
 * 设置域 API：系统状态卡片消费的只读端点。
 *
 * 数据源均为既有/新增的聚合端点（不含任务载荷）：
 * - 后端活性：任一鉴权 GET 的往返延迟（探针，见 probeBackend）
 * - Django-Q：/task-queue/cluster-status（集群心跳 / 队列深度 / 今日成败）
 * - LLM：/llm/models（模型面）、/agent/usage（AI 任务成功率与耗时）、
 *   /llm/test-connection（管理员显式连通性测试）
 */

import { api } from '@/lib/api'

/** Django-Q 集群活性（clusters=null 表示无法探测，≠ 0 个集群） */
export interface QClusterStatus {
  clusters: number | null
  queue_depth: number
  succeeded_today: number
  failed_today: number
  last_success_at: string | null
  last_failed_at: string | null
  broker_error: string | null
}

export interface LlmModelInfo {
  id: string
  name: string
  backend: string
  context_window: number
}

/** /agent/usage 的消费投影（只取状态卡要看的字段） */
export interface AgentUsageSummary {
  runs: number
  ok_runs: number
  error_runs: number
  cancelled_runs: number
  error_rate: number
  avg_duration_ms: number
}

export interface LlmTestResult {
  ok: boolean
  model?: string
  backend?: string
  error?: string
}

export async function fetchQClusterStatus(): Promise<QClusterStatus> {
  return api.get('task-queue/cluster-status').json<QClusterStatus>()
}

export async function fetchLlmModels(): Promise<LlmModelInfo[]> {
  const res = await api.get('llm/models').json<{ models: LlmModelInfo[] }>()
  return res.models
}

export async function fetchAgentUsage(days = 1): Promise<AgentUsageSummary> {
  return api.get('agent/usage', { searchParams: { days: String(days) } }).json<AgentUsageSummary>()
}

/** 连通性测试（后端限定管理员；无权限时接口会返回错误文案，原样展示） */
export async function testLlmConnection(modelId: string): Promise<LlmTestResult> {
  return api.post('llm/test-connection', { searchParams: { model_id: modelId } }).json<LlmTestResult>()
}

/** 后端活性探针：测一次鉴权 GET 的往返耗时（ms）。请求失败即视为后端不可达。 */
export async function probeBackend(): Promise<number> {
  const startedAt = performance.now()
  await api.get('organization/me').json()
  return Math.round(performance.now() - startedAt)
}
