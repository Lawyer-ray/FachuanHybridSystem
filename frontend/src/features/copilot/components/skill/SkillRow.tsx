/**
 * 技能清单的一行：标题 + slug + 双轨状态徽标 + 描述 + 覆盖关系 + 行内动作。
 *
 * 四件事都在这一行里说清，因为它们互为前提：
 * 1. **状态**（`skillStatusBadge`）：已生效 / 草稿 / 待审（有未发布改动）/ 已驳回 / 已下线；
 * 2. **覆盖关系**（`skillCoverageNotes`）：`/skill:名字` 只会展开赢家，被顶掉的那条
 *    若不明说「被谁覆盖」，律师会以为开关坏了；同名竞争时赢家再补一个「当前生效」
 *    徽标——否则「已生效」与「赢了级联」这两件事在这一行上长得一样；
 * 3. **动作**：全部由服务端 `can_*` 决定——`can_edit` 才有编辑，`can_review &&
 *    review_status==='pending'` 才有审核，`can_promote`/`can_submit` 才有提审。
 *    前端绝不按 `source` 或 `is_admin` 自己推。
 *
 * 开关用 `role="switch"` + `aria-checked` 手写而不是原生 checkbox：原生控件在 WebKit
 * 上的尺寸/配色不可控，与抽屉里其它中性灰阶控件对不齐。
 *
 * 共享技能（团队 / 所内）的开关写的是**本人偏好**，所以可访问名写「仅对我停用」而不是
 * 「停用」——「停用一条所内技能」听起来像是替全所关掉它。
 */

import { ClipboardCheck, Copy, Pencil, Trash2, Upload } from 'lucide-react'

import { StatusBadge } from '@/components/shared/StatusBadge'
import type { AgentSkill } from '../../types'
import { skillCoverageNotes, skillStatusBadge } from './skill-status'

/** 行内图标按钮：默认低对比、hover 才提亮；禁用（请求在途）时压暗 */
const ROW_ACTION_CLASS =
  'flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40'

/** 开关本体（启用态用前景色 70% 的灰，不引入语义色） */
const SWITCH_CLASS = 'relative h-[18px] w-8 flex-none rounded-full transition-colors disabled:opacity-50'
const SWITCH_KNOB_CLASS = 'absolute top-[2px] h-3.5 w-3.5 rounded-full bg-card shadow-sm transition-all'

/** 共享技能的开关只影响本人：可访问名要说全，否则会被读成「替全所停用」 */
function toggleLabel(skill: AgentSkill): string {
  const shared = skill.scope === 'team' || skill.scope === 'law_firm'
  if (shared) return `${skill.enabled ? '仅对我停用' : '仅对我启用'} ${skill.title}`
  return `${skill.enabled ? '停用' : '启用'} ${skill.title}`
}

function SkillSwitch({
  skill,
  disabled,
  onToggle,
}: {
  skill: AgentSkill
  disabled: boolean
  onToggle: (enabled: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={skill.enabled}
      aria-label={toggleLabel(skill)}
      title={skill.scope === 'team' || skill.scope === 'law_firm' ? '只改你自己的使用偏好，不影响其他律师' : undefined}
      disabled={disabled}
      onClick={() => onToggle(!skill.enabled)}
      className={`${SWITCH_CLASS} ${skill.enabled ? 'bg-foreground/70' : 'border border-border bg-secondary'}`}
    >
      <span className={`${SWITCH_KNOB_CLASS} ${skill.enabled ? 'left-4' : 'left-[2px]'}`} />
    </button>
  )
}

export function SkillRow({
  skill,
  busy,
  /** 同名条目 ≥2：赢家行补「当前生效」徽标，让人看清 `/skill:名字` 现在展开哪一条 */
  contended,
  onEdit,
  onDelete,
  onDuplicate,
  onToggle,
  onReview,
  onPromote,
}: {
  skill: AgentSkill
  /** 该行有请求在途（启停/删除/复制）：开关与动作暂时禁用，避免连点打架 */
  busy: boolean
  contended: boolean
  onEdit: (skill: AgentSkill) => void
  onDelete: (skill: AgentSkill) => void
  onDuplicate: (skill: AgentSkill) => void
  onToggle: (skill: AgentSkill, enabled: boolean) => void
  onReview: (skill: AgentSkill) => void
  onPromote: (skill: AgentSkill) => void
}) {
  const badge = skillStatusBadge(skill)
  const notes = skillCoverageNotes(skill)
  // 已下线的条目不在运行时集合里，开关没有意义；恢复入口（`can_restore`）还没接，别在这里假装有
  const togglable = skill.status !== 'archived'
  // 待审 + 有审批权才给「审核」：两个条件都来自服务端（`can_review` 由后端算）
  const reviewable = skill.can_review && skill.review_status === 'pending'
  // 个人条目用 `can_promote`（`can_submit` 对 scope=lawyer 恒 false），共享条目用 `can_submit`
  const promotable = skill.can_promote === true || skill.can_submit
  return (
    <div className="flex items-start gap-2.5 rounded-[9px] border border-border bg-card px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="truncate text-[12.5px] font-medium text-foreground">{skill.title}</span>
          <StatusBadge tone={badge.tone} size="xs" title={badge.hint}>
            {badge.label}
          </StatusBadge>
          {contended && skill.effective ? (
            <StatusBadge
              tone="blue"
              size="xs"
              title={`/skill:${skill.name} 现在展开的是这一条（同名条目里它赢了级联）`}
            >
              当前生效
            </StatusBadge>
          ) : null}
          <code className="truncate font-mono text-[10.5px] text-muted-foreground/80">{skill.name}</code>
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-relaxed text-muted-foreground">{skill.description}</p>
        {notes.map((note) => (
          <p key={note.kind} className="mt-0.5 text-[10.5px] leading-relaxed text-muted-foreground/80">
            {note.text}
          </p>
        ))}
      </div>

      <div className="flex flex-none items-center gap-0.5 pt-0.5">
        {skill.source === 'builtin' ? (
          <button
            type="button"
            aria-label={`复制 ${skill.title} 为我的`}
            title="复制为我的"
            disabled={busy}
            onClick={() => onDuplicate(skill)}
            className={ROW_ACTION_CLASS}
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {reviewable ? (
          <button
            type="button"
            aria-label={`审核 ${skill.title}`}
            title="审核待审改动"
            disabled={busy}
            onClick={() => onReview(skill)}
            className={ROW_ACTION_CLASS}
          >
            <ClipboardCheck className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {promotable ? (
          <button
            type="button"
            aria-label={`提审 ${skill.title}`}
            title={skill.scope === 'lawyer' ? '提审到共享层' : '提交审批'}
            disabled={busy}
            onClick={() => onPromote(skill)}
            className={ROW_ACTION_CLASS}
          >
            <Upload className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {skill.can_edit ? (
          <button
            type="button"
            aria-label={`编辑 ${skill.title}`}
            title="编辑"
            disabled={busy}
            onClick={() => onEdit(skill)}
            className={ROW_ACTION_CLASS}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {skill.can_edit && skill.scope === 'lawyer' ? (
          <button
            type="button"
            aria-label={`删除 ${skill.title}`}
            title="删除"
            disabled={busy}
            onClick={() => onDelete(skill)}
            className={ROW_ACTION_CLASS}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {togglable ? (
          <SkillSwitch skill={skill} disabled={busy} onToggle={(enabled) => onToggle(skill, enabled)} />
        ) : null}
      </div>
    </div>
  )
}
