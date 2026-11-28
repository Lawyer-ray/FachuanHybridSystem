/**
 * Copilot 技能类型：`/` 命令菜单的技能清单、技能详情、校验与配额。
 *
 * 从 `types.ts` 拆出（后者贴近 350 行软红线）。字段口径与后端 P0 契约一致
 * （`docs/analysis/user-skills-copilot-2026-11-28/P0-BRIEF.md` §1.6）：
 * `key` 是身份（`builtin:<name>` / `skill:<uuid>`），`source` 是「内置 / 个人」的
 * 唯一判据——内置的 `scope` 是空串，**不要**靠它判空来区分来源。
 *
 * 端点与请求构造见 `skill-api.ts`（前缀 `agent/skills`，后端
 * `backend/apps/agent/api/skill_api.py`）；消费方是 `domain/slash.ts`（菜单徽标）、
 * `components/SlashMenu.tsx`（展示）与 `components/skill/*`（管理抽屉）。
 */

/** 技能来源：内置只读（可复制为我的），个人可增删改 */
export type AgentSkillSource = 'builtin' | 'user'

/**
 * 技能作用域。P0 只产生 `lawyer`（个人）；`team` / `law_firm` 是三级预留，
 * 内置技能用空串（前端按 `source` 分支，不看 `scope`）。
 */
export type AgentSkillScope = '' | 'lawyer' | 'team' | 'law_firm'

/** GET /agent/skills 的技能清单项 */
export interface AgentSkill {
  /** 身份：`builtin:<name>` / `skill:<uuid>`（启停、详情、编辑都用它，含 `:` 需 URL 编码） */
  key: string
  /** slug：目录名 = `/skill:` 命令名（内置「复制为我的」时沿用） */
  name: string
  /** 显示名 */
  title: string
  /** 单行路由描述（决定 AI 什么时候用它；进系统提示） */
  description: string
  enabled: boolean
  source: AgentSkillSource
  scope: AgentSkillScope
  /** 内置技能不可改（只能复制为我的） */
  editable: boolean
  /** 乐观锁版本：内置为 0；修改时回传，不符后端 409 */
  version: number
}

/** GET /agent/skills 的响应体 */
export interface AgentSkillList {
  skills: AgentSkill[]
}

/** GET /agent/skills/{key}：清单字段 + 正文（编辑器打开时才拉） */
export interface AgentSkillDetail extends AgentSkill {
  body: string
}

/** PATCH /agent/skills/{key} 的回执（只改启停偏好，不改正文） */
export interface AgentSkillToggleReceipt {
  key: string
  enabled: boolean
}

/** 新建 / 校验的请求体（`name` 省略 = 后端生成 `skill-<6位base36>`） */
export interface AgentSkillCreateInput {
  name?: string
  title: string
  description: string
  body: string
}

/** 修改的请求体（`name` 建后不可改；`version` 不符后端 409，编辑器保留草稿） */
export interface AgentSkillUpdateInput {
  title: string
  description: string
  body: string
  version: number
}

/** 字段级校验错误（`field` 是表单字段名：name/title/description/body） */
export interface AgentSkillValidationError {
  field: string
  message: string
}

/** POST /agent/skills/validate 的回执：`preview` 是「AI 实际读到的 SKILL.md」 */
export interface AgentSkillValidation {
  ok: boolean
  errors: AgentSkillValidationError[]
  preview: string
}

/** GET /agent/skills/quota：个人技能配额（界面上限 20） */
export interface AgentSkillQuota {
  max_skills: number
  used: number
}
