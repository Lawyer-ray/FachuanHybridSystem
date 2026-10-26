/**
 * `/` 命令菜单的交互状态（键盘导航 + 选中分发）。
 *
 * 纯领域逻辑（构建/过滤）在 domain.ts；本 hook 只管交互态：
 * - 菜单开着时 ↑/↓ 换选中、Enter/Tab 生效（不发送消息）、Esc 关闭
 * - Esc 关闭后查询词不变期间不再弹出（改字才重新触发）
 * - 选中禁用项（无会话时的 compact）不生效也不发送
 * onKeyDown 返回 true 表示事件已被菜单消费，调用方必须短路后续发送逻辑。
 */

import { useEffect, useMemo, useState } from 'react'

import { buildSlashMenuItems, filterSlashMenuItems, slashMenuQuery } from '../domain'
import type { AgentSkill, SlashMenuItem } from '../types'

export interface UseSlashMenuOptions {
  /** 当前输入框文本（决定菜单开关与过滤词） */
  text: string
  /** 技能清单（react-query 缓存；只消费 enabled 项） */
  skills: AgentSkill[]
  /** 是否有活动会话（无会话时 compact 禁用） */
  hasSession: boolean
  /** 选中技能：调用方把文本替换为 `/skill:名字 ` */
  onSkill: (name: string) => void
  /** 选中命令：调用方执行动作并清空输入 */
  onCommand: (id: string) => void
}

export function useSlashMenu({ text, skills, hasSession, onSkill, onCommand }: UseSlashMenuOptions) {
  const [index, setIndex] = useState(0)
  /** Esc 关闭时的查询词：同一查询词不再弹（改字重新触发） */
  const [dismissed, setDismissed] = useState<string | null>(null)

  const query = slashMenuQuery(text)
  const allItems = useMemo(() => buildSlashMenuItems(skills, hasSession), [skills, hasSession])
  const items = useMemo(() => (query === null ? [] : filterSlashMenuItems(allItems, query)), [allItems, query])
  const open = query !== null && query !== dismissed

  // 过滤结果变化后选中项复位到首个可用项（禁用项不可作为初始选中）
  useEffect(() => {
    setIndex(Math.max(0, items.findIndex((i) => !i.disabled)))
  }, [items])

  const apply = (item: SlashMenuItem | undefined): boolean => {
    if (!item || item.disabled) return true // 吃掉按键但不动作（也不发送）
    setDismissed(null)
    if (item.kind === 'skill') onSkill(item.id)
    else onCommand(item.id)
    return true
  }

  const onKeyDown = (e: React.KeyboardEvent): boolean => {
    if (!open) return false
    if (e.key === 'Escape') {
      setDismissed(query)
      return true
    }
    if (items.length === 0) return false
    const enabledIdx = items.map((i, k) => (i.disabled ? -1 : k)).filter((k) => k >= 0)
    const cycle = (delta: number) => {
      const pos = enabledIdx.indexOf(index)
      // 无可用项（全禁用）时导航是 no-op；正常时环形移动
      if (enabledIdx.length > 0) {
        const next = enabledIdx[(pos + delta + enabledIdx.length) % enabledIdx.length] ?? 0
        setIndex(next)
      }
    }
    switch (e.key) {
      case 'ArrowDown':
        cycle(1)
        return true
      case 'ArrowUp':
        cycle(-1)
        return true
      case 'Enter':
      case 'Tab':
        return apply(items[index])
      default:
        return false
    }
  }

  return { open, items, index, setIndex, onKeyDown, apply }
}
