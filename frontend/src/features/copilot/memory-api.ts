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

// 域类型住在 `memory-types.ts`（与 `scope-types.ts` / `skill-types.ts` 同构）：
// 本文件只 import 进来供签名使用，并 re-export 一次保持既有 `from './memory-api'`
// 的 import 路径可用（新增代码请从 `./types` 引）。
import type {
  AgentMemoryItem,
  MemoryKind,
  MemoryScopes,
  MemoryScope,
  MemoryStatus,
  PromoteCandidate,
} from './memory-types'

export type {
  AgentMemoryItem,
  MemoryKind,
  MemoryScopes,
  MemoryScope,
  MemoryStatus,
  PromoteCandidate,
} from './memory-types'

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
  /** 律所层必填 true：提交者确认过「全对全所所有律师生效」。 */
  acknowledgedFirmWide?: boolean
}): Promise<AgentMemoryItem> {
  return api
    .post('agent/memory/promotion', {
      json: {
        source_ids: payload.sourceIds,
        content: payload.content,
        kind: payload.kind,
        scope: payload.scope,
        team_id: payload.teamId ?? null,
        acknowledged_firm_wide: payload.acknowledgedFirmWide ?? false,
      },
    })
    .json<AgentMemoryItem>()
}

/**
 * 项目笔记的回执（`POST /agent/memory/notes` 的 `MemoryOut` 子集）。
 *
 * 本组端点从 `api.ts` 并入本文件：前缀同为 `agent/memory`，与会话 CRUD 无关；
 * `api.ts` 仍 re-export，既有 import 路径不变。
 */
export interface ProjectNoteReceipt {
  id: string
  content: string
  contract_id: number | null
  case_id: number | null
  /** 非空 = 已有人点过确认（项目事实）；空 = 同事的判断 */
  confirmed_at: string
}

/**
 * 把一条结论存进项目笔记（同团队可见）。
 *
 * **只传 sessionId**：前端拿不到可靠的 `contract_id`（案件页的 `CopilotScope`
 * 只有 case_id），让前端猜锚点必然把结论写到错的项目上。锚点由服务端按会话
 * 归属反查，会话不属于自己时按「没有锚点」处理。
 */
export function createProjectNote(input: {
  content: string
  sessionId: string
  kind?: string
}): Promise<ProjectNoteReceipt> {
  return api
    .post('agent/memory/notes', {
      json: {
        content: input.content,
        session_id: input.sessionId,
        ...(input.kind ? { kind: input.kind } : {}),
      },
    })
    .json<ProjectNoteReceipt>()
}
