/**
 * 记忆域类型：条目、策展候选与可策展作用域。
 *
 * 与 `scope-types.ts` / `skill-types.ts` 同构——域类型住在 `xxx-types.ts`，
 * 不再内嵌在 API 客户端里（原先住在 `memory-api.ts`，改一个类型的 import 路径
 * 要动 8 个组件）。`types.ts` 统一 re-export，组件一律从 `../../types` 引。
 *
 * 端点与请求构造见 `memory-api.ts`（前缀 `agent/memory`，后端
 * `backend/apps/agent/api/memory_api.py`）。
 */

/** 记忆作用域 */
export type MemoryScope = 'lawyer' | 'team' | 'law_firm'

/** 记忆类型：纠正 > 偏好 > 惯例 > 事实（注入优先级同序） */
export type MemoryKind = 'fact' | 'preference' | 'procedure' | 'correction' | 'playbook'

/** 待确认 = 自动抽取/行为推断产出，确认后才进上下文 */
export type MemoryStatus = 'pending' | 'active' | 'deleted'

/**
 * 操作指引：长篇多步骤规范（阅卷流程/立案步骤/归档规则）。
 *
 * 与短规则的通道不同——它不进每轮注入（注入层单条上限 200 字、律所层配额
 * 700 字，36 行的规范塞进去会被直接跳过、律师还以为记忆坏了），只在记忆块
 * 里留一行索引，模型需要时用 recall_memory 取全文。
 */
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
