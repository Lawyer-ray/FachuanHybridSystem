/**
 * 抽屉 tab 的口径：哪几个 tab 出现、每个 tab 对应哪个作用域、配额怎么对齐。
 *
 * 可见性**只由两件事决定**：服务端给了哪些条目（`GET /skills` 已按可见性过滤——
 * 管理员才看得到本所待审 / 已下线），以及服务端算好的 `can_create_firm`。
 * 前端绝不判 `is_admin`：那既重复了一套权限口径，也会在「管理员但无所内条目」
 * 这类边界上与后端打架。团队 tab 同理——`can_create_team` 需要指定团队，归发布
 * 对话框（另 lane）处理，本文件只认「有没有团队条目」。
 */

import type { AgentSkill, AgentSkillQuota, AgentSkillScope } from '../../types'

import { SKILL_SCOPE_LABELS } from './skill-status'

/** 四个 tab 的身份。顺序即展示顺序（个人 → 所内 → 团队 → 系统） */
export type SkillTabId = 'mine' | 'firm' | 'team' | 'system'

/**
 * 抽屉里能直接新建的层。
 *
 * 所内要服务端 `can_create_firm`（只有本所管理员能直建所内草稿）；团队要选具体团队，
 * 归发布对话框（另 lane），所以在抽屉里永远拿不到 `team`。
 */
export type SkillCreateScope = 'lawyer' | 'law_firm'

/** tab → 作用域（分列表、对齐配额都用它，避免两处各写一份字符串） */
const TAB_SCOPE: Record<SkillTabId, AgentSkillScope> = {
  mine: 'lawyer',
  firm: 'law_firm',
  team: 'team',
  system: 'builtin',
}

/** 固定顺序：`visibleSkillTabs` 按它筛，不做动态排序（tab 位置漂移会让人点错） */
const TAB_ORDER: readonly SkillTabId[] = ['mine', 'firm', 'team', 'system']

export function skillTabScope(tab: SkillTabId): AgentSkillScope {
  return TAB_SCOPE[tab]
}

/** tab 文案与作用域标签同一套（「所内」既是 tab 名也是层级名，不另造说法） */
export function skillTabLabel(tab: SkillTabId): string {
  return SKILL_SCOPE_LABELS[TAB_SCOPE[tab]]
}

/** 条目属于哪个 tab（只比作用域，不比来源：`source` 是交付面的说法） */
export function skillInTab(skill: AgentSkill, tab: SkillTabId): boolean {
  return skill.scope === TAB_SCOPE[tab]
}

/** 作用域 → 该去哪个 tab（保存成功后切过去；新建所内技能的返回值也走这里） */
export function skillTabForScope(scope: AgentSkillScope): SkillTabId {
  return TAB_ORDER.find((tab) => TAB_SCOPE[tab] === scope) ?? 'mine'
}

/**
 * 当前可见的 tab。
 *
 * - 「我的」「系统」恒在（侧栏入口一打开就得有落点，空态本身要能引导新建）；
 * - 「所内」在「有条目」或「服务端允许直建所内草稿」时出现：后者对应管理员首次
 *   进抽屉——此时没有条目，但必须给得到入口，否则所内层永远发不出第一条；
 * - 「团队」只在有条目时出现（见文件头：团队新建要选团队，归发布对话框）。
 */
export function visibleSkillTabs(skills: AgentSkill[], quota?: AgentSkillQuota): SkillTabId[] {
  const hasScope = (scope: AgentSkillScope) => skills.some((skill) => skill.scope === scope)
  return TAB_ORDER.filter((tab) => {
    if (tab === 'mine' || tab === 'system') return true
    if (tab === 'firm') return hasScope('law_firm') || quota?.can_create_firm === true
    return hasScope('team')
  })
}

/**
 * tab 角标要显示的待审条数：只数「服务端说我能审」的条目。
 *
 * 不另要一个计数字段：清单本身已经是服务端按可见性过滤过的，再要一个数只会有
 * 两份口径（角标 3、点进去 2 条）。旧后端没有 `review_status` 时归一化为 `none`，
 * 角标自然不出现。
 */
export function skillTabPendingCount(skills: AgentSkill[], tab: SkillTabId): number {
  return skills.filter((skill) => skillInTab(skill, tab) && skill.review_status === 'pending' && skill.can_review).length
}

/** 当前 tab 的配额格 */
export interface SkillTabQuotaCell {
  used: number
  max: number
  full: boolean
  /** 满了之后要写清原因（只在配额条上写一处，新建按钮用 title 复用同一句） */
  fullReason: string
}

/**
 * 取当前 tab 的 `used / max`。
 *
 * 系统技能不占配额（随代码发布），返回 null；某层 `max` 为 0 表示服务端没给这一层
 * 的上限（旧后端只有个人层），返回 null——拿 0 当「已满」会把新建入口关死。
 */
export function skillTabQuota(tab: SkillTabId, quota?: AgentSkillQuota): SkillTabQuotaCell | null {
  if (!quota) return null
  const scope = TAB_SCOPE[tab]
  // 系统技能随代码发布、不占配额（同时也把 `scope` 收窄回可索引计数表的三层）
  if (scope === 'builtin') return null
  const max = quota.max_by_scope[scope]
  if (max <= 0) return null
  const used = quota.by_scope[scope]
  const label = skillTabLabel(tab)
  return {
    used,
    max,
    full: used >= max,
    fullReason: `${label}技能已达上限 ${used}/${max}，先下线不用的技能再新建`,
  }
}
