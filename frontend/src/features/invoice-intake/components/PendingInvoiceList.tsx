import { isRed, type IntakeGroup } from '../domain'
import type { InvoiceIntake } from '../types'
import { RedReenactCard } from './RedReenactCard'
import { InvoiceIntakeRow } from './InvoiceIntakeRow'

/**
 * 待认领列表的「组 + 单行」渲染段（从 PendingInvoicesCard 拆出，控制主件规模）。
 *
 * 只做渲染：数据来源、mutation、弹窗目标全部由调用方（PendingInvoicesCard）持有，
 * 这里不引入任何自己的状态——否则两处都会有一份「当前在处理哪张票」的真相。
 *
 * 分工是固定的：`groups` 走 {@link RedReenactCard}（原票/红票/新票三段、一次请求
 * 完成整组），`standalones` 走 {@link InvoiceIntakeRow}（普通蓝票）。
 */
export function PendingInvoiceList({
  groups,
  standalones,
  busy,
  redBusy,
  onConfirmRow,
  onChangeRow,
  onDetail,
  onConfirmReenact,
  onConfirmRedOnly,
  onReparse,
}: {
  groups: IntakeGroup[]
  standalones: InvoiceIntake[]
  /** 普通票确认 mutation 是否在跑 */
  busy: boolean
  /** 红票整组动作（重开 / 仅冲红 / 重解析）是否有在跑的 */
  redBusy: boolean
  onConfirmRow: (intake: InvoiceIntake) => void
  onChangeRow: (intake: InvoiceIntake) => void
  onDetail: (intake: InvoiceIntake) => void
  onConfirmReenact: (red: InvoiceIntake, newIntakeId: number | null) => void
  onConfirmRedOnly: (red: InvoiceIntake) => void
  onReparse: (red: InvoiceIntake) => void
}) {
  return (
    <>
      {groups.map((group) => {
        // 组内一定有红票（后端按红票建组）；防御性兜底：找不到就整组跳过
        const red = group.items.find(isRed)
        if (!red?.reatch_group) return null
        const reissue = red.reatch_group.reissue
        return (
          <div key={`group-${group.groupKey}`} className="mb-1.5 last:mb-0">
            <RedReenactCard
              group={red.reatch_group}
              red={red}
              busy={redBusy}
              // `new_intake_id` 可空：后端会按组内成员自己认重开的那张
              onConfirmReenact={() => onConfirmReenact(red, reissue?.intake_id ?? null)}
              onConfirmOnly={() => onConfirmRedOnly(red)}
              onReparse={() => onReparse(red)}
              onDetail={() => onDetail(red)}
            />
          </div>
        )
      })}

      {standalones.map((intake) => (
        <div key={intake.id} className="mb-1.5 last:mb-0">
          <InvoiceIntakeRow
            intake={intake}
            busy={busy}
            // 采纳系统建议：直接绑定、不二次确认（金额、购买方、建议项目与匹配
            // 信号都已在眼前，多一次弹窗只是重复阅读同一批信息）
            onConfirm={() => onConfirmRow(intake)}
            onChange={() => onChangeRow(intake)}
            onDetail={() => onDetail(intake)}
          />
        </div>
      ))}
    </>
  )
}
