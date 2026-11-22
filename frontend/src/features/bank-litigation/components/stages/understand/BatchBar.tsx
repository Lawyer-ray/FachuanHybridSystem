/**
 * ② 读懂的批量操作条：全选 / 已选计数 / 批量重转。
 *
 * 批量条有自己的状态（选中的文档、重转进度），但它不是面板的编排，
 * 所以单独一个组件：面板只把 `checked` 与 `batchRun` 传进来。
 */

import { Play } from 'lucide-react'

import { ActionButton, WorkCard } from '../../ui'
import type { StageActionState } from '../use-stage-action'

export function BatchBar({
  checkedCount,
  total,
  allChecked,
  onToggleAll,
  batch,
  onRun,
}: {
  checkedCount: number
  total: number
  allChecked: boolean
  onToggleAll: () => void
  /** 批量重转的当前状态（只用到 phase / percent / progress / summary） */
  batch: StageActionState
  onRun: () => void
}) {
  return (
      <WorkCard className="flex flex-wrap items-center gap-2 py-2.5">
        <ActionButton
          sm
          onClick={() =>
            onToggleAll()
          }
        >
          {allChecked ? '全不选' : '全选'}
        </ActionButton>
        <span className="text-[11px] text-muted-foreground">
          已选 {checkedCount} / {total} 份
        </span>
        <span className="ml-auto flex items-center gap-2">
          {batch.phase === 'running' ? (
            <span className="text-[10.5px] tabular-nums text-muted-foreground">
              {batch.percent}% · {batch.progress}
            </span>
          ) : batch.phase === 'done' ? (
            <span className="text-[10.5px] text-status-green">{batch.summary}</span>
          ) : null}
          <ActionButton
            sm
            dark
            disabled={checkedCount === 0 || batch.phase === 'running'}
            onClick={() => onRun()}
          >
            <Play className="size-3" /> 批量重转{checkedCount ? ` ${checkedCount} 份` : ''}
          </ActionButton>
        </span>
      </WorkCard>
  )
}
