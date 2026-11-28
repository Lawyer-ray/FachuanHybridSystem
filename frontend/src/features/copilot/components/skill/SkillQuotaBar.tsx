/**
 * 当前 tab 的配额条（`used / max` + 满额原因）。
 *
 * 为什么按 tab 分而不是给一条总配额：三层的上限互不相干（个人 20 / 团队 30 / 所内 60，
 * 见后端 `constants`），混成一条会让「所内还剩 47 条」看起来像「我的还能建」。
 *
 * 满额时**必须写原因**：按钮被禁用却不说为什么，律师只会反复点。原因文案由
 * `skill-tabs.ts` 给出，新建按钮的 `title` 复用同一句，两处不会漂移；配额格由
 * `use-skill-drawer-state` 算一次后同时喂给本条与列表（不各算一次，免得两处判据漂移）。
 */

import { skillTabLabel, type SkillTabId, type SkillTabQuotaCell } from './skill-tabs'

export function SkillQuotaBar({ tab, cell }: { tab: SkillTabId; cell: SkillTabQuotaCell | null }) {
  // 系统技能不占配额；旧后端没给这一层上限（max=0）时也不假装有配额
  if (!cell) return null
  const percent = Math.min(100, Math.round((cell.used / cell.max) * 100))
  const label = skillTabLabel(tab)
  return (
    <div className="mb-2.5">
      <div className="flex items-baseline justify-between text-[11px] text-muted-foreground">
        <span>{label}配额</span>
        <span className={cell.full ? 'font-medium text-destructive' : undefined}>
          已用 {cell.used} / {cell.max}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={`${label}配额已用`}
        aria-valuenow={cell.used}
        aria-valuemin={0}
        aria-valuemax={cell.max}
        className="mt-1 h-1 overflow-hidden rounded-full bg-secondary"
      >
        <div
          className={`h-full rounded-full transition-[width] ${cell.full ? 'bg-destructive' : 'bg-foreground/40'}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {cell.full ? <p className="mt-1 text-[10.5px] leading-relaxed text-destructive">{cell.fullReason}</p> : null}
    </div>
  )
}
