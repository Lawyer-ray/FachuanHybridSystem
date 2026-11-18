/**
 * Copilot 技能类型：`/` 命令菜单的技能清单与启停回执。
 *
 * 从 `types.ts` 拆出（后者贴近 350 行软红线）。三个端点形状放在一起，
 * 消费方见 `domain/slash.ts`（菜单构建）与 `components/SlashMenu.tsx`（展示）。
 */

/** GET /agent/skills 的技能清单项（消息以 `/skill:名字 参数` 触发展开全文） */
export interface AgentSkill {
  name: string
  description: string
  enabled: boolean
}

/** GET /agent/skills 的响应体 */
export interface AgentSkillList {
  skills: AgentSkill[]
}

/** PATCH /agent/skills/{name} 的回执 */
export interface AgentSkillToggleReceipt {
  name: string
  enabled: boolean
}
