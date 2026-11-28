/**
 * 技能行的「状态口径」纯函数：双轨徽标与覆盖关系文案。
 *
 * 为什么单独成文件：徽标与覆盖提示是**判断**（哪条状态优先、文案怎么说），不是渲染。
 * 它们要在列表行（`SkillRow`）、测试与将来的审批面板里用同一份口径，写成纯函数
 * 才能一处改、三处一致；放在 `components/skill/` 而不是 `domain/` 是因为本 lane 的
 * 文件边界只到「技能子域 + `domain/slash.ts`」，而这些口径也只服务这个子域。
 *
 * 铁律：本文件**不判权限**。`can_*` / `review_status` 都是服务端算好的事实，
 * 这里只决定怎么显示；任何「是不是管理员」的推断都不属于前端。
 */

import type { Tone } from '@/lib/tone'

import type { AgentSkill, AgentSkillScope } from '../../types'

/** 作用域 → 中文标签（与后端 `constants.SCOPE_LABELS` 同口径，一套说法不分裂） */
export const SKILL_SCOPE_LABELS: Record<AgentSkillScope, string> = {
  builtin: '系统',
  lawyer: '我的',
  team: '团队',
  law_firm: '所内',
}

export function skillScopeLabel(scope: AgentSkillScope): string {
  return SKILL_SCOPE_LABELS[scope]
}

/** 一行上要显示的双轨状态徽标 */
export interface SkillStatusBadge {
  tone: Tone
  label: string
  /** 悬停解释：驳回理由是 `review_note`（律师要能一眼看到为什么被驳回） */
  hint: string
}

/**
 * 双轨状态徽标：先看线上槽位（已下线），再看修订流（驳回 / 待审），最后才是草稿 / 生效。
 *
 * 顺序不能反：已下线的条目也可能还挂着待审，先显示「待审」会让人以为它快要上线了；
 * 而「待审」必须区分有没有未发布改动——律师最常问的就是「我现在改了，线上到底变没变」。
 */
export function skillStatusBadge(skill: AgentSkill): SkillStatusBadge {
  if (skill.status === 'archived') {
    return { tone: 'neutral', label: '已下线', hint: '已下线，不再交给 AI；恢复后要重新提审才会生效' }
  }
  if (skill.review_status === 'rejected') {
    return { tone: 'red', label: '已驳回', hint: skill.review_note || '审批未通过，按驳回理由修改后可重新提审' }
  }
  if (skill.review_status === 'pending') {
    return skill.has_unpublished_changes
      ? { tone: 'yellow', label: '待审（有未发布改动）', hint: '等待审批；线上仍是上一版已批准内容，这次改动还没生效' }
      : { tone: 'yellow', label: '待审', hint: '等待审批，通过后才会生效' }
  }
  if (skill.status === 'draft') {
    return { tone: 'neutral', label: '草稿', hint: '还没有发布过，只有你自己能看到' }
  }
  return { tone: 'green', label: '已生效', hint: 'AI 点名时可以取到这条技能（支持提示注入的后端还会看到它的索引行）' }
}

/** 覆盖关系的一行提示 */
export interface SkillCoverageNote {
  kind: 'shadowed' | 'shadows'
  text: string
}

/**
 * 覆盖关系提示。
 *
 * - `shadowed_by` 非空 = 本条被更高优先级的同名技能顶掉（`/skill:名字` 会展开赢家），
 *   必须写出赢家的**中文名**——律师认的是「合同审查三段式」，不是 `contract-review`；
 * - `shadowed` 非空 = 本条顶掉了更低优先级的同名条目（列表里不能让它静默消失）。
 */
export function skillCoverageNotes(skill: AgentSkill): SkillCoverageNote[] {
  const notes: SkillCoverageNote[] = []
  if (skill.shadowed_by) {
    const by = skill.shadowed_by
    notes.push({ kind: 'shadowed', text: `被「${skillScopeLabel(by.scope)}」同名技能「${by.title}」覆盖` })
  }
  if (skill.shadowed.length > 0) {
    notes.push({ kind: 'shadows', text: `覆盖了${shadowedSummary(skill.shadowed)}` })
  }
  return notes
}

/** 「覆盖了所内版」/「覆盖了所内版等 2 个同名技能」：只报层级，具体标题进详情再看 */
function shadowedSummary(shadowed: AgentSkill['shadowed']): string {
  const layers = [...new Set(shadowed.map((item) => item.scope))]
  const first = layerName(layers[0])
  if (layers.length === 1) return first
  return `${first}等 ${layers.length} 个同名技能`
}

/** 单层时的口语说法带「版」：律师说的是「所内版顶掉了我的」，不是「所内层」 */
function layerName(scope: AgentSkillScope | undefined): string {
  switch (scope) {
    case 'law_firm':
      return '所内版'
    case 'team':
      return '团队版'
    case 'builtin':
      return '系统版'
    default:
      return '我的同名版本'
  }
}
