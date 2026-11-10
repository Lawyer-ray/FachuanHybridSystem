import { useMemo, useState } from 'react'
import { FileText } from 'lucide-react'

import { CardHead } from '@/components/shared/CardHead'
import { PANEL } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
import { useConfirmInvoiceIntake, usePendingInvoices } from '../hooks/use-pending-invoices'
import type { InvoiceIntake } from '../types'
import { ConfirmedInvoiceRow, type ConfirmedRow } from './ConfirmedInvoiceRow'
import { ContractPicker } from './ContractPicker'
import { InvoiceDetailDialog } from './InvoiceDetailDialog'
import { InvoiceIntakeRow } from './InvoiceIntakeRow'

/**
 * 首页「待认领发票」模块 —— 财务发来的每一张发票都要律师确认绑定才落账。
 *
 * ## 为什么是常驻卡而不是「没有待办就隐藏」
 *
 * 与待认领款项同理：若待办为空就隐藏整卡，用户会怀疑功能没在跑。三种状态
 * 都渲染：有数据 / 空态 / 加载失败（**失败与空态必须分得开**，否则服务端
 * 故障会被读成「没有发票」）。
 *
 * ## bare 模式
 *
 * 首页要把款项 + 发票合成**一张卡**，此时外层 section 与 CardHead 由合成卡提供：
 *
 * ```tsx
 * <section className={PANEL}>
 *   <CardHead title="待认领" count="..." />
 *   <PendingIntakeCard bare />
 *   <PendingInvoicesCard bare />
 * </section>
 * ```
 *
 * `bare=true` 只渲染内容区（含自身分组小标题「发票」），不包 section、不渲染
 * CardHead；`bare=false`（默认）就是独立可用的完整卡片。
 *
 * ## 「换个项目」与「详情」留待接线
 *
 * 本阶段只做骨架：两个动作都接在 `onChange` / `onDetail` 上，实际弹窗
 * （项目选择器 + 发票详情）由后续接线实现。行内的「确认绑定」已是完整链路。
 */
export function PendingInvoicesCard({ bare = false }: { bare?: boolean } = {}) {
  const { data = [], isLoading, isError, error, refetch } = usePendingInvoices(20)

  // 刚确认完、本次浏览期间仍要留着的行（供立刻复制那个重命名后的文件）。
  // **只存内存**：刷新页面即清空 -> 首页只剩真正待办的（用户明确要求）。
  const [justConfirmed, setJustConfirmed] = useState<ConfirmedRow[]>([])
  const confirm = useConfirmInvoiceIntake({
    onConfirmed: ({ intakeId, invoiceId, displayFilename }) => {
      // 购买方/金额从当前列表里取（确认前那一行还在 data 里）；
      // 文件名必须用接口返回的（那是后端命名规则的唯一产物）
      const src = data.find((d) => d.id === intakeId)
      setJustConfirmed((prev) => [
        ...prev.filter((r) => r.intakeId !== intakeId),
        {
          intakeId,
          invoiceId,
          buyerName: src?.buyer_name ?? '',
          totalAmount: src?.total_amount ?? null,
          displayFilename,
        },
      ])
    },
  })

  // 详情弹窗的目标行：点「详情」时定住那一行，弹窗里不跟随列表刷新而漂移
  const [detailFor, setDetailFor] = useState<InvoiceIntake | null>(null)
  // 「换个项目」的目标行：改判需要知道是哪张票
  const [pickerFor, setPickerFor] = useState<InvoiceIntake | null>(null)

  const count = data.length
  const subtitle = useMemo(() => (isError ? '' : count ? `${count} 张` : ''), [count, isError])

  const content = (
    <div className="px-2.5 pt-1.5 pb-2.5">

      {isError && (
        <div className="px-2 py-6 text-center text-[12.5px] text-destructive">
          {errMessage(error, '待认领发票加载失败')}
          <button
            type="button"
            className="ml-1.5 cursor-pointer underline underline-offset-3"
            onClick={() => void refetch()}
          >
            重试
          </button>
        </div>
      )}

      {!isError && isLoading && (
        <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>
      )}

      {!isError &&
        !isLoading &&
        count === 0 &&
        (bare ? (
          /* 合成卡合并展示：空态压成一行，避免两组都空时首页一大块空白 */
          <div className="flex items-center gap-1.5 px-2 py-2 text-[11.5px] text-muted-foreground">
            <FileText className="h-3 w-3 flex-none opacity-50" aria-hidden />
            暂无待认领发票
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
            <FileText className="h-4 w-4 text-muted-foreground/50" aria-hidden />
            <div className="text-[12.5px] text-muted-foreground">暂无待认领发票</div>
            <div className="text-[10.5px] text-muted-foreground/70">财务发来发票邮件后会自动出现在这里</div>
          </div>
        ))}

      {!isError &&
        !isLoading &&
        data.map((intake) => (
          <div key={intake.id} className="mb-1.5 last:mb-0">
            <InvoiceIntakeRow
              intake={intake}
              busy={confirm.isPending}
              // 采纳系统建议：直接绑定，不再二次确认（金额、购买方、建议项目
              // 与匹配信号都已在眼前，多一次弹窗只是重复阅读同一批信息）
              onConfirm={() => confirm.mutate({ id: intake.id })}
              onChange={() => setPickerFor(intake)}
              onDetail={() => setDetailFor(intake)}
            />
          </div>
        ))}

      {/* 刚确认完的行：留在原地供复制，刷新页面即消失 */}
      {justConfirmed.map((row) => (
        <div key={`done-${row.intakeId}`} className="mt-1.5">
          <ConfirmedInvoiceRow row={row} />
        </div>
      ))}
    </div>
  )

  // 合成卡里靠左侧色条（发票=indigo）区分，不再写「发票」文字标签。
  // 上边框只在**本组有内容**时画：本组空态只是一行灰字，再压一条分隔线
  // 会把「没东西」强调成一个小节，反而显乱。
  // 详情弹窗放在最外层（Dialog 本身是 portal，放哪都能覆盖整页）；
  // 两种渲染模式共用同一份，避免各写一遍。
  const picker = (
    <ContractPicker
      open={pickerFor != null}
      onOpenChange={(v) => !v && setPickerFor(null)}
      busy={confirm.isPending}
      onPick={(contractId) => {
        const row = pickerFor
        if (!row) return
        // 改判后**不**带 paymentId：原预选收款是相对原建议合同算的，
        // 换项目后不再成立，先挂项目名下，收款到项目页再关联。
        confirm.mutate({ id: row.id, contractId })
      }}
    />
  )

  const detail = (
    <InvoiceDetailDialog
      intake={detailFor}
      open={detailFor != null}
      onClose={() => setDetailFor(null)}
      onConfirm={(row) => {
        setDetailFor(null)
        confirm.mutate({ id: row.id })
      }}
      busy={confirm.isPending}
    />
  )

  if (bare) {
    return (
      <>
        <div className={`border-l-2 border-l-indigo-400/70 ${count ? 'border-t border-t-border/60' : ''}`}>
          {content}
        </div>
        {detail}
        {picker}
      </>
    )
  }

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="待认领发票" count={subtitle} />
      {content}
      {detail}
      {picker}
    </section>
  )
}
