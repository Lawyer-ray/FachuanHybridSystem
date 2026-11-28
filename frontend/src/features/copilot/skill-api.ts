/**
 * 技能 API 客户端（清单 / 详情 / 增删改 / 校验 / 复制 / 启停 / 配额 / 双轨发布 / 运行时正文）。
 *
 * 端点前缀 `agent/skills`，逐条对齐 `docs/analysis/user-skills-copilot-2026-11-28/CONTRACT.md`
 * §8（静态段 `quota` / `validate` / `resolve` 必须由后端排在 `{key}` 之前，前端只管拼对路径）。
 *
 * 与 `memory-api.ts` 同构：域类型住在 `skill-types.ts`，`api.ts` 只 re-export 旧函数
 * （本文件按职责从 `api.ts` 拆出，后者贴近 350 行软红线）。
 *
 * **所有 `key` 必须 `encodeURIComponent`**：内置 key 含 `:`（`builtin:web-research`），
 * 个人 key 含 `:`（`skill:<uuid>`），原样拼进路径会被 URL 解析吃掉或错位。
 *
 * 归一化只在本文件做一次：`GET /skills` 等回执在 P0 后端上缺 §2 的十几条字段
 * （`status` / `review_status` / `can_*` …），让组件各自补默认值必然互相打架；
 * 出口统一过 `normalizeAgentSkill`，类型就能保持严格。
 */

import { api } from '@/lib/api'

import type {
  AgentSkill,
  AgentSkillContent,
  AgentSkillCreateInput,
  AgentSkillDetail,
  AgentSkillDiff,
  AgentSkillList,
  AgentSkillQuota,
  AgentSkillReviewInput,
  AgentSkillScope,
  AgentSkillScopeCounts,
  AgentSkillShadowRef,
  AgentSkillSource,
  AgentSkillSubmitInput,
  AgentSkillToggleReceipt,
  AgentSkillUpdateInput,
  AgentSkillValidation,
} from './skill-types'

/** `agent/skills/{encoded key}{suffix}`：key 的编码只在这一处做，避免某个端点漏编。
 *
 * 导出给 `skill-trial-api.ts`（试跑域拆出去后仍要拼同一套路径）——两处各写一份
 * `encodeURIComponent` 的那天，就是某个端点漏编码的那天。
 */
export function skillPath(key: string, suffix = ''): string {
  return `agent/skills/${encodeURIComponent(key)}${suffix}`
}

// ── 归一化（服务端字段缺省的唯一降级点）────────────────────────

/** 服务端回执的最小形状：这五个字段任何版本都有，其余按契约可能缺省 */
type AgentSkillWire = Partial<AgentSkill> & Pick<AgentSkill, 'key' | 'name' | 'title' | 'description'>

/** 作用域 → 级联权重（与后端 `constants.SCOPE_WEIGHT` 同口径） */
const SCOPE_WEIGHT: Record<AgentSkillScope, number> = { builtin: -1, lawyer: 0, team: 1, law_firm: 2 }

const KNOWN_SCOPES = new Set<AgentSkillScope>(['builtin', 'lawyer', 'team', 'law_firm'])
const KNOWN_SOURCES = new Set<AgentSkillSource>(['builtin', 'user', 'team', 'law_firm'])

/** 只认白名单里的作用域：未知字符串一律当缺省（不让服务端新枚举值把界面搞崩） */
function parseScope(value: unknown): AgentSkillScope | null {
  return typeof value === 'string' && KNOWN_SCOPES.has(value as AgentSkillScope) ? (value as AgentSkillScope) : null
}

/** `scope` 缺省 / 是 P0 的空串时按 `source` 回落（两者在服务端是同一件事的两种写法） */
function scopeOf(raw: AgentSkillWire): AgentSkillScope {
  return parseScope(raw.scope) ?? parseScope(raw.source) ?? 'lawyer'
}

/** `source` 缺省时按 `scope` 反推：个人条目在线上叫 `user`，作用域叫 `lawyer` */
function sourceOf(raw: AgentSkillWire, scope: AgentSkillScope): AgentSkillSource {
  return raw.source && KNOWN_SOURCES.has(raw.source) ? raw.source : scope === 'lawyer' ? 'user' : scope
}

function shadowRefOf(raw: unknown): AgentSkillShadowRef | null {
  if (!raw || typeof raw !== 'object') return null
  const item = raw as { key?: unknown; scope?: unknown; title?: unknown }
  if (typeof item.key !== 'string') return null
  return {
    key: item.key,
    scope: parseScope(item.scope) ?? 'lawyer',
    title: typeof item.title === 'string' ? item.title : '',
  }
}

/**
 * 清单项归一化：缺省字段按「最保守且不说谎」的值补齐。
 *
 * - `enabled` / `version` / `editable` 缺省时取 P0 语义（存在即可用、版本 0、不可改）；
 * - `status` / `review_status` 缺省 → `active` / `none`（P1 之前创建即生效）；
 * - `can_submit` / `can_review` / `can_archive` / `can_restore` 缺省 → **false**：
 *   服务端没表态的能力一律不出入口，绝不拿 `editable` 或 `is_admin` 猜；
 * - 只有 `can_edit` 缺省时回落到 `editable`——那是服务端自己算的字段，回落不会
 *   越权，还能让旧后端上的个人技能编辑入口不因这次升级消失。
 */
export function normalizeAgentSkill(raw: AgentSkillWire): AgentSkill {
  const scope = scopeOf(raw)
  const source = sourceOf(raw, scope)
  const editable = raw.editable ?? false
  const version = raw.version ?? 0
  return {
    key: raw.key,
    name: raw.name,
    title: raw.title,
    description: raw.description,
    scope,
    scope_weight: raw.scope_weight ?? SCOPE_WEIGHT[scope],
    source,
    enabled: raw.enabled ?? true,
    editable,
    version,
    status: raw.status ?? 'active',
    review_status: raw.review_status ?? 'none',
    review_note: raw.review_note ?? '',
    published_version: raw.published_version ?? version,
    has_unpublished_changes: raw.has_unpublished_changes ?? false,
    shadowed: (raw.shadowed ?? []).flatMap((item) => shadowRefOf(item) ?? []),
    // 旧后端只返回胜出条目（没有遮蔽概念），缺省 true 才是它当时的真话
    effective: raw.effective ?? true,
    shadowed_by: shadowRefOf(raw.shadowed_by),
    can_edit: raw.can_edit ?? editable,
    can_submit: raw.can_submit ?? false,
    can_review: raw.can_review ?? false,
    can_archive: raw.can_archive ?? false,
    can_restore: raw.can_restore ?? false,
    // 提升能力位与可选目标层：与上面五处不同，这里**不补默认值**——缺省的含义是
    // 「服务端没表态」，界面的正确反应是不出提升入口，而不是猜一个 true 出来。
    // 注意本函数是显式构造对象：**任何新增的服务端字段都必须在这段里透传**，否则
    // 会被静默丢掉，症状是「入口永不出现」而不是报错，属于最难查的一类。
    can_promote: raw.can_promote,
    promotable_scopes: raw.promotable_scopes,
  }
}

function normalizeAgentSkillDetail(raw: AgentSkillWire & { body?: string }): AgentSkillDetail {
  return { ...normalizeAgentSkill(raw), body: raw.body ?? '' }
}

type AgentSkillQuotaWire = Partial<AgentSkillQuota> & Pick<AgentSkillQuota, 'max_skills' | 'used'>

/**
 * 配额归一化：旧后端只有 `{max_skills, used}`，补一份只有个人层的 `by_scope` /
 * `max_by_scope`。共享层上限留 0 表示「服务端没说」——界面据此不显示该层配额条、
 * 也不禁用新建（详见 `AgentSkillQuota.max_by_scope` 注释）。
 */
export function normalizeAgentSkillQuota(raw: AgentSkillQuotaWire): AgentSkillQuota {
  const counts: AgentSkillScopeCounts = {
    lawyer: raw.by_scope?.lawyer ?? raw.used,
    team: raw.by_scope?.team ?? 0,
    law_firm: raw.by_scope?.law_firm ?? 0,
  }
  return {
    max_skills: raw.max_skills,
    used: raw.used,
    by_scope: counts,
    max_by_scope: {
      lawyer: raw.max_by_scope?.lawyer ?? raw.max_skills,
      team: raw.max_by_scope?.team ?? 0,
      law_firm: raw.max_by_scope?.law_firm ?? 0,
    },
    can_create_firm: raw.can_create_firm ?? false,
  }
}

// ── 清单 / 详情 / 配额 ────────────────────────────────────────

/**
 * 技能清单（`/` 命令菜单与技能抽屉共用的数据源）。
 *
 * `scope` 省略 = 全部层（服务端 `list_visible_skills` 已按可见性过滤，前端不再过滤
 * 一次：前端过滤会把「管理员可见的待审条目」这类判断变成第二套权限口径）。
 */
export async function fetchAgentSkills(scope?: AgentSkillScope | 'all'): Promise<AgentSkillList> {
  const url = scope && scope !== 'all' ? `agent/skills?scope=${encodeURIComponent(scope)}` : 'agent/skills'
  const raw = await api.get(url).json<{ skills?: AgentSkillWire[] }>()
  return { skills: (raw.skills ?? []).map((item) => normalizeAgentSkill(item)) }
}

/** 技能详情（含工作区正文；编辑器打开时才拉） */
export async function fetchAgentSkill(key: string): Promise<AgentSkillDetail> {
  const raw = await api.get(skillPath(key)).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/** 技能配额（当前 tab 的 `used / max` 与「能否直建所内」） */
export async function fetchAgentSkillQuota(): Promise<AgentSkillQuota> {
  const raw = await api.get('agent/skills/quota').json<AgentSkillQuotaWire>()
  return normalizeAgentSkillQuota(raw)
}

/**
 * 运行时正文（MCP `get_agent_skill` 的同一条出口，`start` 按字节翻页）。
 *
 * 抽屉/编辑器不用它（那里读的是工作区草稿），它是「模型实际读到什么」的证据来源。
 */
export function fetchAgentSkillContent(ref: string, start = 0): Promise<AgentSkillContent> {
  return api.get(`agent/skills/resolve/${encodeURIComponent(ref)}/content?start=${start}`).json<AgentSkillContent>()
}

// ── 写动作 ────────────────────────────────────────────────────

/** 新建技能（`scope` 省略 = 个人；`scope='law_firm'` 需服务端 `can_create_firm`） */
export async function createAgentSkill(input: AgentSkillCreateInput): Promise<AgentSkill> {
  const raw = await api.post('agent/skills', { json: input }).json<AgentSkillWire>()
  return normalizeAgentSkill(raw)
}

/** 修改（`version` 是乐观锁；不符后端 409，调用方保留草稿） */
export async function updateAgentSkill(key: string, input: AgentSkillUpdateInput): Promise<AgentSkill> {
  const raw = await api.put(skillPath(key), { json: input }).json<AgentSkillWire>()
  return normalizeAgentSkill(raw)
}

/** 删除个人技能（内置 403；成功 204 无响应体） */
export async function deleteAgentSkill(key: string): Promise<void> {
  await api.delete(skillPath(key))
}

/** 校验草稿并拿回「AI 实际读到的内容」预览（保存前必调，错误按字段定位） */
export function validateAgentSkill(input: AgentSkillCreateInput): Promise<AgentSkillValidation> {
  return api.post('agent/skills/validate', { json: input }).json<AgentSkillValidation>()
}

/** 复制内置技能为我的（个人技能 403） */
export async function duplicateAgentSkill(key: string): Promise<AgentSkill> {
  const raw = await api.post(skillPath(key, '/duplicate')).json<AgentSkillWire>()
  return normalizeAgentSkill(raw)
}

/** 启停一个技能（个人改本体；内置 / 共享只写本人偏好，返回终态回执） */
export function setAgentSkillEnabled(key: string, enabled: boolean): Promise<AgentSkillToggleReceipt> {
  return api.patch(skillPath(key), { json: { enabled } }).json<AgentSkillToggleReceipt>()
}

// ── 双轨发布（提审 / 审批 / 下线 / 恢复 / 放弃草稿 / diff）────────

/** 提审：把工作区提交给审批人（**不动线上**，旧版继续生效） */
export async function submitAgentSkill(key: string, input: AgentSkillSubmitInput): Promise<AgentSkillDetail> {
  const raw = await api.post(skillPath(key, '/submit'), { json: input }).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/** 审批：通过（升为线上生效版）或驳回（`note` 必填） */
export async function reviewAgentSkill(key: string, input: AgentSkillReviewInput): Promise<AgentSkillDetail> {
  const raw = await api.post(skillPath(key, '/review'), { json: input }).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/** 下线（`status='archived'`，立即退出运行时解析；保留占名与快照） */
export async function archiveAgentSkill(key: string): Promise<AgentSkillDetail> {
  const raw = await api.post(skillPath(key, '/archive')).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/** 恢复：`archived → draft`（必须重走提审，不能一键复活） */
export async function restoreAgentSkill(key: string): Promise<AgentSkillDetail> {
  const raw = await api.post(skillPath(key, '/restore')).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/**
 * 放弃工作区改动：把线上已批准版回填到工作区，清掉待审 / 驳回态。
 *
 * 路径用 `/discard-draft`（服务端 `review.discard_draft`）；CONTRACT §8 的端点表
 * 没有这一条，属本 lane 与后端 lane 需要对齐的一处（见交付回报「契约偏差」）。
 */
export async function discardAgentSkillDraft(key: string): Promise<AgentSkillDetail> {
  const raw = await api.post(skillPath(key, '/discard-draft')).json<AgentSkillWire & { body?: string }>()
  return normalizeAgentSkillDetail(raw)
}

/** 两版对比（缺省「线上生效版 vs 工作区」；首次发布时两侧相同，hunks 只有 equal） */
export function fetchAgentSkillDiff(key: string, v1?: number, v2?: number): Promise<AgentSkillDiff> {
  const params = new URLSearchParams()
  if (v1 !== undefined) params.set('v1', String(v1))
  if (v2 !== undefined) params.set('v2', String(v2))
  const query = params.toString() ? `?${params.toString()}` : ''
  return api.get(skillPath(key, `/diff${query}`)).json<AgentSkillDiff>()
}

/** 试跑域（慢端点 + 额度）搬进 `skill-trial-api.ts`，import 路径不变。 */
export {
  fetchAgentSkillTrialQuota,
  normalizeAgentSkillTrial,
  normalizeAgentSkillTrialQuota,
  runAgentSkillTrial,
} from './skill-trial-api'
