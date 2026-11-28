/**
 * `/` 命令菜单的纯函数：命令清单、技能 + 命令合并、输入过滤与触发判定。
 */

import type { AgentSkill, SlashMenuItem } from '../types'

/** 内置命令（不走 `/skill:` 文本协议：RPC 模式下 pi 内置命令不是文本，由前端直调端点） */
export const SLASH_COMMANDS: Array<Pick<SlashMenuItem, 'kind' | 'id' | 'label' | 'description'>> = [
  { kind: 'command', id: 'compact', label: '压缩上下文', description: '总结当前会话历史，释放上下文空间（保留案号/期限等锚点）' },
  { kind: 'command', id: 'manage-skills', label: '管理技能', description: '查看、新建、编辑我的技能' },
]

/**
 * 技能清单 + 内置命令 → 菜单项。
 *
 * 技能只列已启用的，并带 `badge`（我的 / 系统）——同名时用户要能分清这条
 * `/skill:名` 是自己写的还是内置的。compact 无活动会话时禁用；`manage-skills`
 * 与弹抽屉的入口不依赖会话，恒可用。
 *
 * `title` 必须带过来：律师给技能起的是中文名，`/` 菜单要显示它、也要能搜到它
 * （只留 slug 等于逼人背自己没写过的名字）。命令项没有 `title`。
 */
export function buildSlashMenuItems(skills: AgentSkill[], hasSession: boolean): SlashMenuItem[] {
  const skillItems: SlashMenuItem[] = skills
    .filter((s) => s.enabled)
    .map((s) => ({
      key: `skill-${s.key}`,
      kind: 'skill' as const,
      id: s.name,
      label: s.name,
      title: s.title,
      description: s.description,
      badge: s.source === 'user' ? '我的' : '系统',
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
