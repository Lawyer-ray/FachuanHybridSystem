/**
 * ③ 缺件 —— 批量操作条（全选 / 已选计数 / 批量催办 / 批量标记已收 / 清空 / 回执）。
 *
 * 两个批量动作各有自己的执行态，所以这一块自己持有批量执行状态与回执文案：
 * 批量催办只发给「勾选里还没补齐」的项，批量标记已收是行政确认纸质件到了。
 */
import { CheckCircle2, CheckSquare, Square } from 'lucide-react'
import { useState } from 'react'

import { ActionButton } from '../../ui'
import { useStageAction } from '../use-stage-action'

/** 批量操作条 */
export function GapBatchBar({
  checked,
  checkedOpen,
  allChecked,
  onToggleAll,
  onClear,
}: {
  checked: Set<string>
  /** 勾选里还没补齐的那些 —— 只有它们会被催办 / 标记已收 */
  checkedOpen: string[]
  allChecked: boolean
  onToggleAll: () => void
  onClear: () => void
}) {
  /** 演示：批量操作回执 */
  const [batchNote, setBatchNote] = useState('')

  /* 批量催办：把勾选里未补齐的一次性催出去 */
  const batchRemind = useStageAction({
    steps: [
      { text: '汇总勾选项', ms: 260, fixed: true },
      { text: '发送催办短信（含免登录上传链接）', ms: 620 },
      { text: '同步给客户经理与主办律师', ms: 300 },
    ],
    toSummary: () => '已批量催办',
  })
  /* 批量标记已收：行政确认纸质件到了，不用等系统识别 */
  const batchReceive = useStageAction({
    steps: [
      { text: '核对纸质件签收记录', ms: 420 },
      { text: '写入槽位并标记「已收」', ms: 560 },
      { text: '重跑缺件检测', ms: 480 },
    ],
    toSummary: () => '已批量标记已收',
  })
  const batchRunning = batchRemind.phase === 'running' || batchReceive.phase === 'running'

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-border-light bg-secondary/25 px-5 py-2">
        <button
          type="button"
          onClick={onToggleAll}
          aria-label={allChecked ? '取消全选' : '全选当前分组'}
          className="flex items-center gap-1 text-[11px] text-secondary-foreground"
        >
          {allChecked ? (
            <CheckSquare className="size-3.5 text-foreground" />
          ) : (
            <Square className="size-3.5 text-muted-foreground" />
          )}
          {allChecked ? '取消全选' : '全选'}
        </button>
        <span className="text-[10.5px] tabular-nums text-muted-foreground">已选 {checkedOpen.length} 项</span>
        <div className="ml-auto flex items-center gap-1.5">
          <ActionButton
            sm
            dark
            disabled={checkedOpen.length === 0 || batchRunning}
            onClick={() => {
              setBatchNote('')
              void batchRemind.execute().then(() =>
                setBatchNote(`已批量催办 ${checkedOpen.length} 项：${checkedOpen.join('、')}`),
              )
            }}
          >
            {batchRemind.phase === 'running' ? '催办中…' : '批量催办'}
          </ActionButton>
          <ActionButton
            sm
            disabled={checkedOpen.length === 0 || batchRunning}
            onClick={() => {
              setBatchNote('')
              void batchReceive.execute().then(() =>
                setBatchNote(`已批量标记已收 ${checkedOpen.length} 项：${checkedOpen.join('、')}`),
              )
            }}
          >
            {batchReceive.phase === 'running' ? '处理中…' : '批量标记已收'}
          </ActionButton>
          {checked.size > 0 ? (
            <ActionButton
              sm
              onClick={() => {
                onClear()
                setBatchNote('')
              }}
            >
              清空
            </ActionButton>
          ) : null}
        </div>
      </div>
      {batchNote ? (
        <div className="flex items-center gap-1.5 border-b border-border-light bg-status-green-bg/40 px-5 py-1.5 text-[10.5px] text-status-green">
          <CheckCircle2 className="size-3" />
          {batchNote}
        </div>
      ) : null}
    </>
  )
}
