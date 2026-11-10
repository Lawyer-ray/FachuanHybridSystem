import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { Wallet } from 'lucide-react'

import { CardHead } from '@/components/shared/CardHead'
import { PANEL } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
import { useConfirmIntake, usePendingIntakes } from '../hooks/use-pending-intakes'
import type { Intake } from '../types'
import { ConfirmDialog } from './ConfirmDialog'
import { IntakeRow } from './IntakeRow'
import { ProjectPicker } from './ProjectPicker'

/**
 * 首页「待认领款项」模块 —— 每一笔到账都要人工确认才记账。
 *
 * ## 为什么是常驻卡而不是"没有待办就隐藏"
 *
 * 用户明确要求「每次进首页都能看到」。若待办为空就隐藏整卡，用户会怀疑
 * 功能没在跑。所以三种状态都渲染：有数据 / 空态 / 加载失败（失败与空态必须
 * 分得开，否则服务端故障会被读成"没有到账"）。
 *
 * ## 交互路径
 *
 * - **确认**：采纳系统建议（只在有实名命中的建议时可用）→ 二次确认 → 写入收款记录
 * - **换个项目**：搜索选择合格项目 → 二次确认 → 写入该项目的收款记录
 * - **详情**：跳到收件箱里那封原始邮件，看银行备注全文
 *
 * 系统**不替人做决定**：只有金额吻合的候选不会预选建议，卡片明确提示需要核对。
 */
export function PendingIntakeCard() {
  const navigate = useNavigate()
  const { data = [], isLoading, isError, error, refetch } = usePendingIntakes(20)
  const confirm = useConfirmIntake()

  const [pickerFor, setPickerFor] = useState<Intake | null>(null)
  const [confirmFor, setConfirmFor] = useState<{ intake: Intake; contractId?: number; contractName?: string } | null>(
    null,
  )

  const count = data.length
  const subtitle = useMemo(() => (isError ? '' : count ? `${count} 笔` : ''), [count, isError])

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="待认领款项" count={subtitle} />
      <div className="px-2.5 pt-1.5 pb-2.5">
        {isError && (
          <div className="px-2 py-6 text-center text-[12.5px] text-destructive">
            {errMessage(error, '待认领款项加载失败')}
            <button type="button" className="ml-1.5 cursor-pointer underline underline-offset-3" onClick={() => void refetch()}>
              重试
            </button>
          </div>
        )}

        {!isError && isLoading && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>
        )}

        {!isError && !isLoading && count === 0 && (
          <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
            <Wallet className="h-4 w-4 text-muted-foreground/50" aria-hidden />
            <div className="text-[12.5px] text-muted-foreground">暂无待认领款项</div>
            <div className="text-[10.5px] text-muted-foreground/70">收到银行到账通知后会自动出现在这里</div>
          </div>
        )}

        {!isError &&
          !isLoading &&
          data.map((intake) => (
            <div key={intake.id} className="mb-1.5 last:mb-0">
              <IntakeRow
                intake={intake}
                busy={confirm.isPending}
                onConfirm={() => setConfirmFor({ intake })}
                onChange={() => setPickerFor(intake)}
                onDetail={() => void navigate(`/material-prep?message=${intake.inbox_message_id}`)}
              />
            </div>
          ))}
      </div>

      <ProjectPicker
        open={pickerFor != null}
        onOpenChange={(open) => !open && setPickerFor(null)}
        initialKeyword=""
        busy={confirm.isPending}
        onPick={(contractId) => {
          const intake = pickerFor
          if (!intake) return
          setPickerFor(null)
          // 选完项目还要走一次二次确认：写入财务数据不该两步并一步
          setConfirmFor({ intake, contractId, contractName: undefined })
        }}
      />

      <ConfirmDialog
        intake={confirmFor?.intake ?? null}
        contractName={confirmFor?.contractName}
        open={confirmFor != null}
        onOpenChange={(open) => !open && setConfirmFor(null)}
        busy={confirm.isPending}
        onConfirm={() => {
          if (!confirmFor) return
          confirm.mutate(
            { id: confirmFor.intake.id, contractId: confirmFor.contractId },
            { onSettled: () => setConfirmFor(null) },
          )
        }}
      />
    </section>
  )
}
