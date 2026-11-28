/**
 * 抽屉的 tab 栏（我的 / 所内 / 团队 / 系统）。
 *
 * 只渲染 `skill-tabs.ts` 算出来的可见 tab：哪个 tab 该出现是「服务端给了什么 +
 * `can_create_firm`」的结论，不是本组件的判断——把可见性逻辑留在纯函数里，
 * 测试能直接断言口径，组件里就不需要 `if (isAdmin)`。
 *
 * 待审角标只数「服务端说我能审」的条目（`can_review`）：角标是提示待办，不是权限。
 * 角标对屏幕阅读器隐藏（数字留在按钮 `title` 里），否则 tab 的可访问名会变成
 * 「所内（1 条待你审批）」，`getByRole('tab', { name: '所内' })` 这类断言全线失配。
 */

import type { AgentSkill, AgentSkillQuota } from '../../types'

import { skillTabLabel, skillTabPendingCount, visibleSkillTabs, type SkillTabId } from './skill-tabs'

export function SkillTabs({
  skills,
  quota,
  active,
  onChange,
}: {
  /** 全量清单（可见性看的是所有层，不是当前 tab） */
  skills: AgentSkill[]
  quota?: AgentSkillQuota
  active: SkillTabId
  onChange: (tab: SkillTabId) => void
}) {
  const tabs = visibleSkillTabs(skills, quota)
  return (
    <div role="tablist" aria-label="技能来源" className="mb-2 flex gap-1 rounded-[7px] bg-secondary/60 p-[3px]">
      {tabs.map((tab) => {
        const label = skillTabLabel(tab)
        const pending = skillTabPendingCount(skills, tab)
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active === tab}
            title={pending > 0 ? `${label}（${pending} 条待你审批）` : undefined}
            onClick={() => onChange(tab)}
            className={`flex flex-1 items-center justify-center rounded-[5px] px-2 py-1 text-[11.5px] font-medium transition-colors ${
              active === tab ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
            {pending > 0 ? (
              <span
                aria-hidden="true"
                className="ml-1 rounded-full bg-status-yellow-bg px-1 text-[10px] leading-[1.5] font-semibold text-status-yellow"
              >
                {pending}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
