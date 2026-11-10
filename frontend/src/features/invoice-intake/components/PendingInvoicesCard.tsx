import { useMemo } from 'react'
import { FileText } from 'lucide-react'

import { CardHead } from '@/components/shared/CardHead'
import { PANEL } from '@/components/shared/panel-styles'
import { errMessage } from '@/lib/errors'
import { useConfirmInvoiceIntake, usePendingInvoices } from '../hooks/use-pending-invoices'
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
  const confirm = useConfirmInvoiceIntake()

  const count = data.length
  const subtitle = useMemo(() => (isError ? '' : count ? `${count} 张` : ''), [count, isError])

  const content = (
    <div className="px-2.5 pt-1.5 pb-2.5">
      {/* 合成卡内部分组：bare 模式下外层没有本组标题，这里补一个 */}
      {bare && <div className="mb-1 px-1 text-[11px] font-[650] text-muted-foreground">发票</div>}

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

      {!isError && !isLoading && count === 0 && (
        <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
          <FileText className="h-4 w-4 text-muted-foreground/50" aria-hidden />
          <div className="text-[12.5px] text-muted-foreground">暂无待认领发票</div>
          <div className="text-[10.5px] text-muted-foreground/70">财务发来发票邮件后会自动出现在这里</div>
        </div>
      )}

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
              onChange={() => console.warn('invoice-intake: 「换个项目」弹窗尚未接线', intake.id)}
              onDetail={() => console.warn('invoice-intake: 发票详情弹窗尚未接线', intake.id)}
            />
          </div>
        ))}
    </div>
  )

  if (bare) return content

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="待认领发票" count={subtitle} />
      {content}
    </section>
  )
}
