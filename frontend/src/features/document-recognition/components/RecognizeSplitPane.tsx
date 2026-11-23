import type { Dispatch, RefObject, SetStateAction } from 'react'

import { cn } from '@/lib/utils'

import { patchRowWithOverride, type CandidateRow } from '../domain'
import type { RecognitionInfo, TaskOut } from '../types'
import { CaseBindingSection } from './CaseBindingSection'
import { DateCandidateList } from './DateCandidateList'
import { DocumentPreview } from './DocumentPreview'
import { PipelineBindingChip } from './PipelineBindingChip'
import { RecognitionSummary } from './RecognitionSummary'
import { StepCard } from './StepCard'

interface Props {
  /** 分栏容器的 ref（左栏宽度按它的实际像素宽换算百分比） */
  bodyRef: RefObject<HTMLDivElement | null>
  /** 任一手柄在拖：整块加 pointer-events-none，避免拖过 iframe 时事件被子文档接走 */
  resizing: boolean
  /** 有可预览原文（换票成功）。没有则单栏铺满 */
  hasPreview: boolean
  previewUrl: string
  splitPct: number
  draggingSplit: boolean
  onStartDragSplit: () => void
  isFileMode: boolean
  /** 法院短信旁线：案件由短信侧绑定，不展示案件选择 */
  isAttached: boolean
  task: TaskOut | null
  recognition: RecognitionInfo | null | undefined
  rows: CandidateRow[]
  busy: boolean
  /** 绑定案件后重拉任务态 */
  onBound: () => Promise<void>
  setOverrides: Dispatch<SetStateAction<Record<string, Partial<CandidateRow>>>>
  onSkip: (row: CandidateRow) => void
  onRevoke: (row: CandidateRow) => void
}

/**
 * 识别弹窗的「左原文 / 右确认步骤」分栏区（lg 双栏，窄屏单栏整体滚动）。
 *
 * 从 RecognizeDialog 抽出来的原因：这段是纯装配——左侧预览 + 拖拽手柄 + 右侧
 * 三步卡片，没有任何自己的状态。留在主组件里会把「弹窗怎么开、什么时候提交、
 * 什么时候接管旁线任务」这些真正的决策淹没在 JSX 里。
 *
 * 责任边界：宽度百分比与拖拽中标记都由调用方持有（useSplitDrag），这里只画；
 * 行内编辑的 overrides、跳过/撤销动作同理由调用方的 hook 提供。
 *
 * 左栏宽度走容器上的 `--split-w` 变量：拖拽中由 hook 直改（零 setState），
 * 这里的 `var(--split-w, <splitPct>%)` 缺省值就是已提交的百分比，首帧即正确。
 * 变量写在容器上而不是左栏本身，是因为拖拽换算百分比用的是容器的实际像素宽。
 */
export function RecognizeSplitPane({
  bodyRef,
  resizing,
  hasPreview,
  previewUrl,
  splitPct,
  draggingSplit,
  onStartDragSplit,
  isFileMode,
  isAttached,
  task,
  recognition,
  rows,
  busy,
  onBound,
  setOverrides,
  onSkip,
  onRevoke,
}: Props) {
  return (
    <div ref={bodyRef} className={cn('flex min-h-0 flex-1 pt-1 lg:overflow-hidden', resizing && 'pointer-events-none')}>
      {hasPreview && (
        <div
          className={cn(
            'hidden min-w-0 flex-col lg:flex',
            draggingSplit && 'pointer-events-none',
          )}
          style={{ width: `var(--split-w, ${splitPct}%)` }}
        >
          <DocumentPreview
            url={previewUrl}
            className={cn('min-h-0 flex-1', !draggingSplit && 'animate-in fade-in slide-in-from-left-2 duration-300')}
          />
        </div>
      )}

      {hasPreview && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整原文宽度"
          title="拖动调整宽度"
          onMouseDown={(e) => {
            e.preventDefault()
            onStartDragSplit()
          }}
          className="group hidden w-[9px] flex-none cursor-col-resize items-center justify-center lg:flex"
        >
          <span
            className={cn(
              'h-full w-[3px] rounded-full transition-colors duration-150',
              draggingSplit ? 'bg-status-blue' : 'bg-transparent group-hover:bg-border',
            )}
          />
        </div>
      )}

      <div
        className={cn(
          'flex min-w-0 animate-in fade-in flex-col gap-3 duration-300 lg:min-h-0 lg:overflow-y-auto lg:pr-1',
          !hasPreview && 'w-full',
          hasPreview && 'flex-1 lg:pl-1.5',
        )}
      >
        {isFileMode && task && recognition && (
          <StepCard title="识别结果">
            <RecognitionSummary task={task} recognition={recognition} previewUrl={previewUrl} />
          </StepCard>
        )}

        {/* 旁线（法院短信）不展示案件选择：案件/日志由短信侧绑定，
            日期写到哪份日历不能在同一张弹窗里被换掉 */}
        {isFileMode && task && (
          <StepCard step={isAttached ? undefined : 1} title="关联案件" muted>
            {isAttached ? (
              <PipelineBindingChip task={task} />
            ) : (
              <CaseBindingSection task={task} onBound={onBound} />
            )}
          </StepCard>
        )}

        <StepCard
          step={isFileMode ? (isAttached ? undefined : 2) : undefined}
          title={isFileMode ? '确认关键日期' : '确认日期'}
          trailing={
            rows.length > 0 ? (
              <span className="text-[11px] font-normal text-muted-foreground">
                {rows.filter((r) => r.status === 'confirmed').length}/{rows.length} 已确认
              </span>
            ) : undefined
          }
        >
          <DateCandidateList
            rows={rows}
            interactive={isFileMode}
            busy={busy}
            onToggle={(key) => {
              const row = rows.find((r) => r.key === key)
              if (row) setOverrides((prev) => ({ ...prev, [key]: { checked: !row.checked } }))
            }}
            onPatch={(key, patch) => setOverrides((prev) => patchRowWithOverride(prev, key, patch))}
            onSkip={onSkip}
            onRevoke={onRevoke}
          />
          {rows.length > 0 && rows.every((r) => r.status !== 'pending') && (
            <span className="mt-1 block text-center text-[11.5px] text-status-green">全部处理完成</span>
          )}
        </StepCard>
      </div>
    </div>
  )
}
