/**
 * 策展对话框左栏：提升目标选择 + 候选池（成员记忆，按共识度排序）。
 *
 * 从 MemoryPromoteDialog 拆出（后者超软红线）。候选行上的「需脱敏」来自后端
 * `pii_risk`，与改写框的本地粗筛（`pii.ts`）互补：前者是客观命中，后者实时提示。
 */

import { ShieldAlert } from 'lucide-react'

import type { MemoryScopes, PromoteCandidate } from '../../memory-api'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { KIND_LABEL } from './labels'

export function PromoteCandidatesPanel({
  target,
  teamId,
  scopes,
  candidates,
  loading,
  selected,
  onTargetChange,
  onToggleSelected,
}: {
  target: 'team' | 'law_firm'
  teamId: number | null
  scopes: MemoryScopes | undefined
  candidates: PromoteCandidate[]
  loading: boolean
  selected: string[]
  /** 切目标：换团队/换层都要清空已选（旧候选的 id 不属于新池） */
  onTargetChange: (target: 'team' | 'law_firm', teamId: number | null) => void
  onToggleSelected: (id: string, checked: boolean) => void
}) {
  const curatableTeams = scopes?.teams.filter((t) => t.can_curate) ?? []
  const canFirm = scopes?.law_firm.can_curate ?? false

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-2 flex flex-none items-center gap-1.5">
        <select
          aria-label="提升目标"
          value={target === 'team' ? `team:${teamId ?? ''}` : 'law_firm'}
          onChange={(e) => {
            const value = e.target.value
            if (value === 'law_firm') {
              onTargetChange('law_firm', null)
              return
            }
            onTargetChange('team', Number(value.split(':')[1]))
          }}
          className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px]"
        >
          {curatableTeams.map((team) => (
            <option key={team.id} value={`team:${team.id}`}>
              {team.name}（团队）
            </option>
          ))}
          {canFirm && <option value="law_firm">全所</option>}
        </select>
        <span className="text-[11px] text-muted-foreground">已选 {selected.length}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto rounded-[10px] border border-border">
        {loading ? (
          <LoadingBlock size="sm" className="py-4" />
        ) : candidates.length === 0 ? (
          <EmptyBlock className="items-start px-3 py-4 text-left leading-relaxed">
            暂无可提炼的成员记忆。等成员积累了一些偏好后，这里会按使用频次列出候选。
          </EmptyBlock>
        ) : (
          <ul className="divide-y divide-border">
            {candidates.map((candidate) => {
              const checked = selected.includes(candidate.id)
              return (
                <li key={candidate.id}>
                  <label
                    className={`flex cursor-pointer items-start gap-2 px-2.5 py-2 transition-colors hover:bg-secondary/50 ${
                      checked ? 'bg-secondary/70' : ''
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-1 h-3.5 w-3.5 flex-none"
                      checked={checked}
                      onChange={(e) => onToggleSelected(candidate.id, e.target.checked)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[12.5px] leading-relaxed text-foreground">{candidate.content}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className="rounded-[4px] bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                          {KIND_LABEL[candidate.kind]}
                        </span>
                        {candidate.from_lawyer && (
                          <span className="text-[10px] text-muted-foreground">{candidate.from_lawyer}</span>
                        )}
                        {candidate.hit_count > 0 && (
                          <span className="text-[10px] text-muted-foreground/80">用过 {candidate.hit_count} 次</span>
                        )}
                        {candidate.pii_risk.length > 0 && (
                          <span
                            className="flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-500"
                            title="含敏感信息，改写时务必脱敏"
                          >
                            <ShieldAlert className="h-2.5 w-2.5" />
                            需脱敏
                          </span>
                        )}
                      </span>
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
