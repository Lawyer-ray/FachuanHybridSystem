/**
 * 输入区的 `/` 菜单联动：技能清单取数 + 选中分发 + 补全后的光标复位。
 *
 * 从 `Composer.tsx` 原样抽出（那个文件贴着 350 行软红线）。它与提交管线只有一个
 * 交点——`onKeyDown` 的裁决点仍留在 Composer，因为「@ 引用菜单先于 / 命令菜单」
 * 这条顺序要和发送逻辑写在同一个地方（见 use-composer-submit.ts 文件头）。
 *
 * 三条与抽出前逐字一致的行为：
 * - 清单取数失败**静默降级**为「只有内置命令」：菜单是加速器，不该拦住发消息；
 * - 选中技能走 `applyMention`（与 `@` 共用的改写原语），且命令的 token 按**整行**
 *   算——命令语义是「整行 = 命令 + 参数」，不跟随光标位置；
 * - `manage-skills` 只弹抽屉（编辑器逻辑在 components/skill/），`compact` 走 store。
 */

import { useQuery } from '@tanstack/react-query'
import type { RefObject } from 'react'

import { fetchAgentSkills } from '../api'
import { applyMention, detectMentionToken } from '../domain'
import { useSkillDrawer } from '../skill-drawer'
import { useCopilot } from '../store'
import { useSlashMenu } from './use-slash-menu'

export interface UseSkillSlashOptions {
  /** 当前草稿：过滤词与命令 token 都从它来 */
  text: string
  /** 选中技能后把草稿改写成 `/skill:名字 ` */
  setText: (value: string) => void
  /** 改写后要把焦点与光标送回输入框 */
  textareaRef: RefObject<HTMLTextAreaElement | null>
  /** 光标状态与 textarea 对齐：补全后光标落在参数位（否则再打参数会插到 /skill: 前面） */
  setCaret: (caret: number) => void
}

export function useSkillSlash({ text, setText, textareaRef, setCaret }: UseSkillSlashOptions) {
  const sessionId = useCopilot((s) => s.sessionId)
  const messageCount = useCopilot((s) => s.messages.length)
  const compactContext = useCopilot((s) => s.compactContext)
  const openSkillDrawer = useSkillDrawer((s) => s.openDrawer)

  // 技能清单（`/` 菜单数据源）：键与 `use-skill-mutations` 的 `SKILLS_QUERY_KEY` 必须同键
  // ——抽屉里改完失效它，这里的候选才跟着变。
  const skillsQuery = useQuery({ queryKey: ['agent-skills'], queryFn: () => fetchAgentSkills(), staleTime: 5 * 60_000, retry: false })
  const skills = skillsQuery.data?.skills ?? []

  return useSlashMenu({
    text,
    skills,
    // 无会话（或还没有消息）时 `compact` 禁用：没有上下文可压
    hasSession: Boolean(sessionId && messageCount > 0),
    onSkill: (name) => {
      // 与 `@` 用**同一个改写原语**；token 按整行算，所以显式传 text.length 而不是跟随 caret
      const token = detectMentionToken(text, text.length)
      const next = token?.trigger === '/' ? applyMention(text, token, { insertText: `/skill:${name} ` }) : null
      const value = next?.text ?? `/skill:${name} `
      const caretAt = next?.caret ?? value.length
      setText(value)
      // 光标落到补全后的位置（原先只 focus，光标留在开头，再打参数会插到 /skill: 前面）
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(caretAt, caretAt)
        setCaret(caretAt)
      })
    },
    onCommand: (id) => {
      if (id !== 'compact' && id !== 'manage-skills') return
      setText('')
      // `manage-skills` 只弹抽屉：编辑器逻辑在 components/skill/，不在这
      if (id === 'manage-skills') openSkillDrawer()
      else void compactContext()
    },
  })
}
