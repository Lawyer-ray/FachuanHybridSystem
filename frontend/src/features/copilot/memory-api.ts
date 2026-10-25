/**
 * 记忆 API 客户端（个人 / 团队 / 律所三级）。
 *
 * 端点前缀 `agent/memory`，见 `backend/apps/agent/api/memory_api.py`。
 *
 * ## 为什么快照接口前端不用
 *
 * `/memory/snapshot` 是给 pi 扩展（`pi/memory-inject.ts`）在 `session_start`
 * 拉的注入用快照——它按层限额渲染、带缓存以保证字节稳定。界面要的是可分页、
 * 可筛选、可逐条删除的**原始条目**，语义不同，不能复用快照。前端一律走
 * `listMemories` 这类结构化接口。
 */

import { api } from '@/lib/api'

/** 记忆作用域 */
export type MemoryScope = 'lawyer' | 'team' | 'law_firm'

/** 记忆类型：纠正 > 偏好 > 惯例 > 事实（注入优先级同序） */
export type MemoryKind = 'fact' | 'preference' | 'procedure' | 'correction'

/** 待确认 = 自动抽取/行为推断产出，确认后才进上下文 */
export type MemoryStatus = 'pending' | 'active' | 'deleted'

export interface AgentMemoryItem {
  id: string
  scope: MemoryScope
  kind: MemoryKind
  content: string
  status: MemoryStatus
  confidence: number
  hit_count: number
  created_at: string
  source_session_id: string
}

/** 策展候选：来自团队成员/律所同事的个人记忆 */
export interface PromoteCandidate {
  id: string
  kind: MemoryKind
  content: string
  hit_count: number
  from_lawyer: string
  /** 命中的敏感模式名（身份证/手机号/案号…），非空说明提升前必须脱敏 */
  pii_risk: string[]
}

/** 我可策展的作用域（决定界面是否显示「提升」入口） */
export interface MemoryScopes {
  law_firm: { id: number | null; can_curate: boolean }
  teams: { id: number; name: string; can_curate: boolean }[]
}

export function listMemories(params: {
  scope?: MemoryScope
  status?: MemoryStatus
  limit?: number
} = {}): Promise<AgentMemoryItem[]> {
  const searchParams: Record<string, string | number> = { limit: params.limit ?? 100 }
  if (params.scope) searchParams.scope = params.scope
  if (params.status) searchParams.status = params.status
  return api.get('agent/memory', { searchParams }).json<AgentMemoryItem[]>()
}

/** 手动新增个人记忆（律师主动说「记住…」时的界面入口） */
export function createMemory(content: string, kind: MemoryKind = 'fact'): Promise<AgentMemoryItem> {
  return api.post('agent/memory', { json: { content, kind } }).json<AgentMemoryItem>()
}

/** 软删（可由 restoreMemory 恢复） */
export function forgetMemory(memoryId: string): Promise<{ ok: boolean }> {
  return api.delete(`agent/memory/${memoryId}`).json<{ ok: boolean }>()
}

export function restoreMemory(memoryId: string): Promise<AgentMemoryItem> {
  return api.post(`agent/memory/${memoryId}/restore`, { json: {} }).json<AgentMemoryItem>()
}

/** 确认/否决待确认记忆 */
export function confirmMemories(ids: string[], accept: boolean): Promise<{ ok: boolean; affected: number }> {
  return api.post('agent/memory/confirm', { json: { ids, accept } }).json<{ ok: boolean; affected: number }>()
}

export function fetchMemoryScopes(): Promise<MemoryScopes> {
  return api.get('agent/memory/scopes').json<MemoryScopes>()
}

/** 策展候选池：本团队/本律所成员的个人记忆，按共识度（命中次数）排序 */
export function fetchPromoteCandidates(params: {
  scope: 'team' | 'law_firm'
  teamId?: number
  limit?: number
}): Promise<PromoteCandidate[]> {
  const searchParams: Record<string, string | number> = { scope: params.scope, limit: params.limit ?? 50 }
  if (params.teamId != null) searchParams.team_id = params.teamId
  return api.get('agent/memory/promotion/candidates', { searchParams }).json<PromoteCandidate[]>()
}

/**
 * 策展提升：把选中的人记忆提炼为团队/律所级规则。
 *
 * 后端两道闸门（`memory_service.promote_memory`）：内容不得与来源原文相同
 * （强制改写=脱敏）、不得含敏感信息。前端把同样的规则做前置提示，
 * 让律师一次填对而不是提交后报错。
 */
export function promoteMemory(payload: {
  sourceIds: string[]
  content: string
  kind: MemoryKind
  scope: 'team' | 'law_firm'
  teamId?: number
}): Promise<AgentMemoryItem> {
  return api
    .post('agent/memory/promotion', {
      json: {
        source_ids: payload.sourceIds,
        content: payload.content,
        kind: payload.kind,
        scope: payload.scope,
        team_id: payload.teamId ?? null,
      },
    })
    .json<AgentMemoryItem>()
}
