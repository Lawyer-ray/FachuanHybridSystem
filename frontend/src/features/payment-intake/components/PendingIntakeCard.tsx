import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { Wallet } from 'lucide-react'

import { CardHead } from '@/components/shared/CardHead'
import { PANEL } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
import { useConfirmIntake, usePendingIntakes } from '../hooks/use-pending-intakes'
import type { Intake } from '../types'
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
 * ## 交互
 *
 * - **确认**：采纳系统建议，**点了就直接写入收款记录，不再弹二次确认**
 *   （用户明确要求去掉这一步：卡片上金额、付款人、匹配项目、匹配理由都已在眼前，
 *   再多一次弹窗只是重复阅读同一批信息）。
 * - **换个项目**：先搜选项目，选完才写入——这一步本身就是要人做选择，
 *   所以项目选择弹窗保留（它不是"确认"，是"改判"）。
 * - **详情**：跳到收件箱里那封原始邮件并展开，看银行备注全文。
 *
 * 系统**不替人做决定**：只有金额吻合的候选不会预选建议，卡片明确提示需要核对。
 */
export function PendingIntakeCard({ bare = false }: { bare?: boolean } = {}) {
  const navigate = useNavigate()
  const { data = [], isLoading, isError, error, refetch } = usePendingIntakes(20)
  const confirm = useConfirmIntake()

  const [pickerFor, setPickerFor] = useState<Intake | null>(null)

  const count = data.length
  const subtitle = useMemo(() => (isError ? '' : count ? `${count} 笔` : ''), [count, isError])

  const body = (
    <>
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

        {!isError && !isLoading && count === 0 &&
          (bare ? (
            /* 合成卡里两组合并展示：空态用一行紧凑提示，不再占一块高的空面板 */
            <div className="flex items-center gap-1.5 px-2 py-2 text-[11.5px] text-muted-foreground">
              <Wallet className="h-3 w-3 flex-none opacity-50" aria-hidden />
              暂无待认领款项
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
              <Wallet className="h-4 w-4 text-muted-foreground/50" aria-hidden />
              <div className="text-[12.5px] text-muted-foreground">暂无待认领款项</div>
              <div className="text-[10.5px] text-muted-foreground/70">收到银行到账通知后会自动出现在这里</div>
            </div>
          ))}

        {!isError &&
          !isLoading &&
          data.map((intake) => (
            <div key={intake.id} className="mb-1.5 last:mb-0">
              <IntakeRow
                intake={intake}
                busy={confirm.isPending}
                // 采纳系统建议：直接写入，不再二次确认
                onConfirm={() => confirm.mutate({ id: intake.id })}
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
          // 改判已由人在弹窗里选定项目，这里同样直接写入
          confirm.mutate({ id: intake.id, contractId })
        }}
      />
    </>
  )

  // bare：只给内容区，由调用方（首页合并卡）提供外壳与标题。
  // 默认：自带外壳——单独使用时与改造前完全一致。
  //
  // 合成卡里**不写「款项」文字标题**：两类待办并列在同一个卡里，靠左侧色条
  // （款项=emerald、发票=indigo）与分隔线区分即可；再加两个文字标签只是重复噪声。
  if (bare) {
    return (
      <div className="border-l-2 border-l-emerald-400/70">
        {body}
      </div>
    )
  }

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="待认领款项" count={subtitle} />
      {body}
    </section>
  )
}
