/**
 * 技能 API 客户端（个人技能的清单 / 详情 / 增删改 / 校验 / 复制 / 启停）。
 *
 * 端点前缀 `agent/skills`，见 `backend/apps/agent/api/skill_api.py`（P0 契约
 * `docs/analysis/user-skills-copilot-2026-11-28/P0-BRIEF.md` §1.5）。
 *
 * 与 `memory-api.ts` 同构：域类型住在 `skill-types.ts`，`api.ts` 只 re-export
 * （本文件按职责从 `api.ts` 拆出，后者贴近 350 行软红线）。
 *
 * **所有 `key` 必须 `encodeURIComponent`**：内置 key 含 `:`（`builtin:web-research`），
 * 个人 key 含 `:`（`skill:<uuid>`），原样拼进路径会被 URL 解析吃掉或错位。
 */

import { api } from '@/lib/api'

import type {
  AgentSkill,
  AgentSkillCreateInput,
  AgentSkillDetail,
  AgentSkillList,
  AgentSkillToggleReceipt,
  AgentSkillUpdateInput,
  AgentSkillValidation,
} from './skill-types'

/** `agent/skills/{encoded key}{suffix}`：key 的编码只在这一处做，避免某个端点漏编 */
function skillPath(key: string, suffix = ''): string {
  return `agent/skills/${encodeURIComponent(key)}${suffix}`
}

/** 技能清单（`/` 命令菜单与技能抽屉共用的数据源） */
export function fetchAgentSkills(): Promise<AgentSkillList> {
  return api.get('agent/skills').json<AgentSkillList>()
}

/** 技能详情（含正文；编辑器打开时才拉） */
export function fetchAgentSkill(key: string): Promise<AgentSkillDetail> {
  return api.get(skillPath(key)).json<AgentSkillDetail>()
}

/** 新建个人技能（`name` 省略则由后端生成 `skill-<6位base36>`） */
export function createAgentSkill(input: AgentSkillCreateInput): Promise<AgentSkill> {
  return api.post('agent/skills', { json: input }).json<AgentSkill>()
}

/** 修改个人技能（`version` 是乐观锁；不符后端 409，调用方保留草稿） */
export function updateAgentSkill(key: string, input: AgentSkillUpdateInput): Promise<AgentSkill> {
  return api.put(skillPath(key), { json: input }).json<AgentSkill>()
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
export function duplicateAgentSkill(key: string): Promise<AgentSkill> {
  return api.post(skillPath(key, '/duplicate')).json<AgentSkill>()
}

/** 启停一个技能（个人改行、内置改偏好；返回终态回执） */
export function setAgentSkillEnabled(key: string, enabled: boolean): Promise<AgentSkillToggleReceipt> {
  return api.patch(skillPath(key), { json: { enabled } }).json<AgentSkillToggleReceipt>()
}
