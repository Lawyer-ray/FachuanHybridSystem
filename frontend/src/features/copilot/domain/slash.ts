/**
 * `/` 命令菜单的纯函数：命令清单、技能 + 命令合并、输入过滤与触发判定。
 */

import type { AgentSkill, SlashMenuItem } from '../types'

/** 内置命令（不走 `/skill:` 文本协议：RPC 模式下 pi 内置命令不是文本，由前端直调端点） */
export const SLASH_COMMANDS: Array<Pick<SlashMenuItem, 'kind' | 'id' | 'label' | 'description'>> = [
  { kind: 'command', id: 'compact', label: '压缩上下文', description: '总结当前会话历史，释放上下文空间（保留案号/期限等锚点）' },
]

/** 技能清单 + 内置命令 → 菜单项（技能只列已启用的；compact 无活动会话时禁用） */
export function buildSlashMenuItems(skills: AgentSkill[], hasSession: boolean): SlashMenuItem[] {
  const skillItems: SlashMenuItem[] = skills
    .filter((s) => s.enabled)
    .map((s) => ({ key: `skill-${s.name}`, kind: 'skill' as const, id: s.name, label: s.name, description: s.description }))
  const commandItems: SlashMenuItem[] = SLASH_COMMANDS.map((c) => ({
    key: `command-${c.id}`,
    ...c,
    ...(c.id === 'compact' && !hasSession ? { disabled: true, disabledHint: '先开始对话' } : {}),
  }))
  return [...commandItems, ...skillItems]
}

/**
 * 按输入过滤菜单项。query 是 `/` 之后的文本：
 * - `skill:xxx` 打头 → 只在技能里按名过滤（用户已明确在挑技能）
 * - 其余 → name/label/description/中文标签大小写不敏感子串匹配
 * 无匹配时返回空数组（调用方据此显示「无匹配命令」并保持菜单打开）。
 */
export function filterSlashMenuItems(items: SlashMenuItem[], query: string): SlashMenuItem[] {
  const q = query.trim().toLowerCase()
  if (q.startsWith('skill:')) {
    const rest = q.slice('skill:'.length).trim()
    return items.filter((i) => i.kind === 'skill' && (rest === '' || i.id.includes(rest)))
  }
  if (!q) return items
  return items.filter((i) => i.id.toLowerCase().includes(q) || i.label.toLowerCase().includes(q) || i.description.toLowerCase().includes(q))
}

/** 输入是否应触发菜单（多行输入的第二行起不再触发，避免正常文本被菜单劫持） */
export function slashMenuQuery(text: string): string | null {
  if (!text.startsWith('/') || text.includes('\n')) return null
  return text.slice(1)
}
