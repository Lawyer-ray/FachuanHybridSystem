/**
 * 技能试跑域：`POST /agent/skills/{key}/trial` 与 `GET /agent/skills/trial-quota`。
 *
 * 从 `skill-api.ts` 拆出（后者已贴近 350 行红线）。为什么它值得单独一个文件：
 * 试跑是**慢端点**（3–45 秒起、真起一个模型进程），它的超时、取消、额度、以及
 * 「★ 字段旧后端没有」，都要单独处理；混在 CRUD 里会让「点一下等 45 秒」这条路径
 * 被当成普通列表操作对待（ky 默认超时 10 秒，正好会把正常的长工具试跑误杀成假故障）。
 *
 * 字段对齐后端 `apps/agent/schemas/skill_schemas.py::SkillTrialOut`；带 ★ 的是后续
 * 扩展字段，**缺失即当没有**——补默认值会让界面显示一个从未发生过的模式或额度。
 */

import { api } from '@/lib/api'

import { skillPath } from './skill-api'
import type {
  AgentSkillTrialInput,
  AgentSkillTrialMode,
  AgentSkillTrialQuota,
  AgentSkillTrialResult,
  AgentSkillTrialToolError,
} from './skill-types'

/** 试跑回执的服务端最小形状：除 `ok` / `text` 外都可能缺省（★ 字段旧后端没有） */
type AgentSkillTrialWire = Partial<AgentSkillTrialResult> & Pick<AgentSkillTrialResult, 'ok' | 'text'>

/** 模式白名单：服务端新枚举值不该让界面显示一个读不懂的模式名 */
const TRIAL_MODES: readonly AgentSkillTrialMode[] = ['auto', 'inline', 'index']

/** 工具失败项：缺失返回 `undefined`（≠ 空数组，缺失表示服务端根本没报这一项） */
function trialToolErrors(raw: unknown): AgentSkillTrialToolError[] | undefined {
  if (!Array.isArray(raw)) return undefined
  return raw.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const entry = item as { tool?: unknown; message?: unknown }
    if (typeof entry.tool !== 'string') return []
    return [{ tool: entry.tool, message: typeof entry.message === 'string' ? entry.message : '' }]
  })
}

/**
 * 试跑回执归一化。**新增字段必须在这里透传**，否则前端永远读到 `undefined`
 * （症状是「那块永远不显示」而不是报错）；★ 三项缺失时保持缺失，不补默认值。
 */
export function normalizeAgentSkillTrial(raw: AgentSkillTrialWire): AgentSkillTrialResult {
  return {
    ok: raw.ok,
    text: raw.text,
    backend: raw.backend ?? '',
    // 报不出模型名就给 null（不是空串）：界面据此整项不显示，绝不渲染成 "null"
    model: raw.model ?? null,
    duration_ms: raw.duration_ms ?? 0,
    skill_key: raw.skill_key ?? '',
    skill_name: raw.skill_name ?? '',
    skill_scope: raw.skill_scope ?? '',
    skill_version: raw.skill_version ?? 0,
    injected: raw.injected ?? '',
    tool_calls: raw.tool_calls ?? [],
    error: raw.error ?? '',
    mode: raw.mode && TRIAL_MODES.includes(raw.mode) ? raw.mode : undefined,
    tool_errors: trialToolErrors(raw.tool_errors),
    trial_id: raw.trial_id,
  }
}

/** 额度归一化：`remaining` 缺失时只有给了 `limit` 才推；两者都没有是「不知道额度」，推成 0 会误禁用按钮 */
export function normalizeAgentSkillTrialQuota(raw: Partial<AgentSkillTrialQuota>): AgentSkillTrialQuota {
  const remaining = raw.limit === undefined ? undefined : Math.max(raw.limit - (raw.used ?? 0), 0)
  return { limit: raw.limit, used: raw.used, remaining: raw.remaining ?? remaining, reset_at: raw.reset_at }
}

/** 客户端超时宽于后端硬超时（45s）：ky 默认 10s，用它会把正常的长工具试跑误杀成假故障 */
const TRIAL_TIMEOUT_MS = 120_000

/** 试跑一条技能（**慢端点**，3–45 秒起）。`signal` 是取消：中断即客户端断开，服务端那一轮的临时会话随进程结束回收 */
export async function runAgentSkillTrial(
  key: string,
  input: AgentSkillTrialInput,
  signal?: AbortSignal,
): Promise<AgentSkillTrialResult> {
  const options = { json: input, timeout: TRIAL_TIMEOUT_MS, ...(signal ? { signal } : {}) }
  const raw = await api.post(skillPath(key, '/trial'), options).json<AgentSkillTrialWire>()
  return normalizeAgentSkillTrial(raw)
}

/** 今日试跑额度（★ 端点：后端未升级时 404，调用方按「不知道额度」处理且不禁用按钮） */
export async function fetchAgentSkillTrialQuota(signal?: AbortSignal): Promise<AgentSkillTrialQuota> {
  const raw = await api.get('agent/skills/trial-quota', signal ? { signal } : {}).json<Partial<AgentSkillTrialQuota>>()
  return normalizeAgentSkillTrialQuota(raw)
}
