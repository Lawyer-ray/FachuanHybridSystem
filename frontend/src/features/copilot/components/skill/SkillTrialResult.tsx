/**
 * 试跑结果的纯展示片段：元信息 / 工具面 / 工具失败 / 实际注入块。
 *
 * 从 `SkillTrialPanel.tsx` 抽出（后者要守 350 行软红线）。这里的每一项都是**审批人
 * 判读试跑结果的依据**，所以每条 docstring 写的是「少了它会怎么被误读」：
 *
 * - `TrialMeta` 空项整项不显示（尤其 `model=null`：渲染成 "null" 会让人以为模型坏了）
 * - `ToolErrorList` 的黄块后面必须跟一句「回复可能不是技能的效果」——少了这句，
 *   审批人会把「模型没读到全文」读成「这条技能没效果」，结论正好反过来
 * - `InjectedBlock` 默认收起：注入块可能几 KB，一展开就把回复挤没了
 */

import { useState } from 'react'

import type { AgentSkillTrialMode, AgentSkillTrialResult, AgentSkillTrialToolError } from '../../skill-types'

/** 实际模式的短标签：上面的 label 太长，塞进元信息一行会把 backend 与耗时挤掉 */
const TRIAL_MODE_LABELS: Record<AgentSkillTrialMode, string> = { auto: '自动', inline: '内联全文', index: '真索引' }

/** 工具短名：`mcp__fachuan__get_agent_skill` → `get_agent_skill`（前缀对「谁在取技能」没有信息量） */
function shortToolName(name: string): string {
  const parts = name.split('__')
  return parts[parts.length - 1] || name
}

/** 元信息一行：backend · model · 耗时 · 实际模式（空项整项不显示，尤其 model=null） */
export function TrialMeta({ result }: { result: AgentSkillTrialResult }) {
  const parts = [
    result.backend,
    result.model ?? '',
    result.duration_ms > 0 ? `${(result.duration_ms / 1000).toFixed(1)} 秒` : '',
    result.mode ? TRIAL_MODE_LABELS[result.mode] : '',
  ].filter(Boolean)
  if (parts.length === 0) return null
  return <p className="text-[10.5px] text-muted-foreground">{parts.join(' · ')}</p>
}

/** 本轮真调用过的工具（短名，一眼看出模型是不是自己去取了全文） */
export function ToolCallList({ calls }: { calls: string[] }) {
  return (
    <ul aria-label="本轮调用过的工具" className="flex flex-wrap gap-1">
      {calls.map((call, index) => (
        <li key={`${call}-${index}`}>
          <code className="rounded-[4px] bg-secondary px-1 py-0.5 font-mono text-[10.5px] text-muted-foreground">
            {shortToolName(call)}
          </code>
        </li>
      ))}
    </ul>
  )
}

/** 工具失败：黄色块 + 一句后果。少了这句，审批人会把「模型没读到全文」当成「技能没效果」 */
export function ToolErrorList({ errors }: { errors: AgentSkillTrialToolError[] }) {
  return (
    <div className="mt-2 rounded-[9px] border border-status-yellow/50 bg-status-yellow-bg px-2.5 py-2">
      <ul className="space-y-1">
        {errors.map((error, index) => (
          <li key={`${error.tool}-${index}`} className="text-[11px] leading-relaxed text-foreground">
            模型试图调用 {shortToolName(error.tool)} 但失败：{error.message || '服务端没给出原因'}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[10.5px] leading-relaxed text-status-yellow">
        这说明它没能读到全文，回复可能不是技能的效果——别用这一轮判这条指令写得好不好。
      </p>
    </div>
  )
}

/** 实际注入块：默认收起（它可能有几 KB，一展开就把回复挤没了） */
export function InjectedBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="text-[10.5px] text-muted-foreground underline underline-offset-2"
      >
        模型实际看到的技能原文
      </button>
      {open ? (
        <pre className="mt-1 max-h-[30vh] overflow-auto rounded-[9px] border border-border bg-secondary px-2.5 py-2 font-mono text-[10.5px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
          {text}
        </pre>
      ) : null}
    </div>
  )
}
