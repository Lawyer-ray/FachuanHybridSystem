/**
 * 技能清单的一行：标题 + slug + 描述 + 启停开关 + 行内动作。
 *
 * 两类行的动作不同，这是权限在界面上的唯一表达（后端也同口径）：
 * - **内置**（`source === 'builtin'`）：只能「复制为我的」+ 启停。正文随代码
 *   发布，改了下一版就被覆盖，所以不给编辑/删除入口；
 * - **个人**（`source === 'user'`）：编辑 / 删除 / 启停。
 *
 * 开关用 `role="switch"` + `aria-checked` 手写而不是原生 checkbox：原生控件
 * 在 WebKit 上的尺寸/配色不可控，与抽屉里其它中性灰阶控件对不齐。
 */

import { Copy, Pencil, Trash2 } from 'lucide-react'

import type { AgentSkill } from '../../types'

/** 行内图标按钮：默认低对比、hover 才提亮；禁用（请求在途）时压暗 */
const ROW_ACTION_CLASS =
  'flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40'

/** 开关本体（启用态用前景色 70% 的灰，不引入语义色） */
const SWITCH_CLASS = 'relative h-[18px] w-8 flex-none rounded-full transition-colors disabled:opacity-50'
const SWITCH_KNOB_CLASS = 'absolute top-[2px] h-3.5 w-3.5 rounded-full bg-card shadow-sm transition-all'

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
      aria-label={`${skill.enabled ? '停用' : '启用'} ${skill.title}`}
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
  onEdit,
  onDelete,
  onDuplicate,
  onToggle,
}: {
  skill: AgentSkill
  /** 该行有请求在途（启停/删除）：开关与动作暂时禁用，避免连点打架 */
  busy: boolean
  onEdit: (skill: AgentSkill) => void
  onDelete: (skill: AgentSkill) => void
  onDuplicate: (skill: AgentSkill) => void
  onToggle: (skill: AgentSkill, enabled: boolean) => void
}) {
  return (
    <div className="flex items-start gap-2.5 rounded-[9px] border border-border bg-card px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className="truncate text-[12.5px] font-medium text-foreground">{skill.title}</span>
          <code className="truncate font-mono text-[10.5px] text-muted-foreground/80">{skill.name}</code>
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-relaxed text-muted-foreground">{skill.description}</p>
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
        ) : (
          <>
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
          </>
        )}
        <SkillSwitch skill={skill} disabled={busy} onToggle={(enabled) => onToggle(skill, enabled)} />
      </div>
    </div>
  )
}
