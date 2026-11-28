/**
 * `/` 命令菜单的纯函数：命令清单、技能 + 命令合并、输入过滤与触发判定。
 */

import type { AgentSkill, AgentSkillSource, SlashMenuItem } from '../types'

/** 内置命令（不走 `/skill:` 文本协议：RPC 模式下 pi 内置命令不是文本，由前端直调端点） */
export const SLASH_COMMANDS: Array<Pick<SlashMenuItem, 'kind' | 'id' | 'label' | 'description'>> = [
  { kind: 'command', id: 'compact', label: '压缩上下文', description: '总结当前会话历史，释放上下文空间（保留案号/期限等锚点）' },
  { kind: 'command', id: 'manage-skills', label: '管理技能', description: '查看、新建、编辑与提审技能' },
]

/** 来源 → 菜单徽标：一条 `/skill:名` 到底来自哪一层，点之前就该看得见 */
const SOURCE_BADGE: Record<AgentSkillSource, string> = {
  builtin: '系统',
  user: '我的',
  team: '团队',
  law_firm: '所内',
}

/**
 * 技能清单 + 内置命令 → 菜单项。
 *
 * 只列「启用且实际胜出」的技能：`/skill:名字` 由服务端按级联展开成**赢家**的全文，
 * 把被遮蔽的条目也列出来会让律师发出 `/skill:名` 后拿到另一条的正文（徽标写着
 * 「所内」、展开的却是「我的」版本）。已下线 / 停用同理不进菜单。
 *
 * `effective` 用 `!== false` 而不是 `=== true`：旧后端的清单只有赢家、不带这个字段，
 * 缺省按「生效」处理；严格判 true 会让这一版菜单在旧后端上整块消失。
 *
 * `badge` 写清来源（我的 / 所内 / 团队 / 系统）——同名时用户要能分清这条
 * `/skill:名` 是哪一层写的。compact 无活动会话时禁用；`manage-skills`
 * 与弹抽屉的入口不依赖会话，恒可用。
 *
 * `title` 必须带过来：律师给技能起的是中文名，`/` 菜单要显示它、也要能搜到它
 * （只留 slug 等于逼人背自己没写过的名字）。命令项没有 `title`。
 */
export function buildSlashMenuItems(skills: AgentSkill[], hasSession: boolean): SlashMenuItem[] {
  const skillItems: SlashMenuItem[] = skills
    .filter((s) => s.enabled && s.effective !== false)
    .map((s) => ({
      key: `skill-${s.key}`,
      kind: 'skill' as const,
      id: s.name,
      label: s.name,
      title: s.title,
      description: s.description,
      badge: SOURCE_BADGE[s.source],
    }))
  const commandItems: SlashMenuItem[] = SLASH_COMMANDS.map((c) => ({
    key: `command-${c.id}`,
    ...c,
    ...(c.id === 'compact' && !hasSession ? { disabled: true, disabledHint: '先开始对话' } : {}),
  }))
  return [...commandItems, ...skillItems]
}

/** 技能项按「slug 或中文显示名」匹配：中文子串也要命中，否则记得住中文名也搜不到 */
function matchesNameOrTitle(item: SlashMenuItem, q: string): boolean {
  return item.id.toLowerCase().includes(q) || (item.title?.toLowerCase().includes(q) ?? false)
}

/**
 * 按输入过滤菜单项。query 是 `/` 之后的文本：
 * - `skill:xxx` 打头 → 只在技能里按名/中文名过滤（用户已明确在挑技能）
 * - 其余 → name/title/label/description/中文标签大小写不敏感子串匹配
 * 无匹配时返回空数组（调用方据此显示「无匹配命令」并保持菜单打开）。
 */
export function filterSlashMenuItems(items: SlashMenuItem[], query: string): SlashMenuItem[] {
  const q = query.trim().toLowerCase()
  if (q.startsWith('skill:')) {
    const rest = q.slice('skill:'.length).trim()
    return items.filter((i) => i.kind === 'skill' && (rest === '' || matchesNameOrTitle(i, rest)))
  }
  if (!q) return items
  return items.filter(
    (i) => matchesNameOrTitle(i, q) || i.label.toLowerCase().includes(q) || i.description.toLowerCase().includes(q),
  )
}

/** 输入是否应触发菜单（多行输入的第二行起不再触发，避免正常文本被菜单劫持） */
export function slashMenuQuery(text: string): string | null {
  if (!text.startsWith('/') || text.includes('\n')) return null
  return text.slice(1)
}
