import { stageLabelsToCodes } from '../../contract-enums'
import type { WorkbenchDeal } from '../../types'
import { AddCaseDialog } from './AddCaseDialog'
import { AddDeadlineDialog } from './AddDeadlineDialog'
import { InvoicePoolDialog } from './InvoicePoolDialog'
import { PaymentDialog } from './PaymentDialog'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import type { useDocDirtyGuard } from './use-doc-dirty-guard'

/**
 * 非诉页挂在页面底部的弹窗：记收款 / 发票池 / 新建下一程序案件 / 新增期限 /
 * 未保存改动确认。
 *
 * 抽出来的判据是关注点边界：这些弹窗只由页面状态开合、保存后回刷页面数据，
 * 与左栏的服务事项流 / 阶段表、右栏事实卡都没有渲染关系。**状态与刷新口径仍归
 * 页面**（`payOpen` / `caseOpen` / `deadlineOpen`、`onScheduleChanged` 等），
 * 本组件只做接线，所以没有自己的 useState。
 */
export function NonLitDetailDialogs({
  deal,
  next,
  payOpen,
  onPayClose,
  onPaymentSaved,
  invoiceOpen,
  onInvoiceClose,
  caseOpen,
  onCaseClose,
  onCaseSaved,
  deadlineOpen,
  onDeadlineClose,
  onScheduleSaved,
  doc,
}: {
  deal: WorkbenchDeal
  /** 合同勾选的下一程序（非诉通常没有；只有数据漂移时才出现建案入口） */
  next: string | null
  payOpen: boolean
  onPayClose: () => void
  /** 记收款保存后刷新本页（合同金额 / 收款徽标） */
  onPaymentSaved: () => void
  invoiceOpen: boolean
  onInvoiceClose: () => void
  caseOpen: boolean
  onCaseClose: () => void
  /** 建案保存后刷新合同与案件（页面用 refetchContractAndCases） */
  onCaseSaved: () => void
  deadlineOpen: boolean
  onDeadlineClose: () => void
  /** 期限保存后刷新合同 + 案件 + 案件直挂提醒 */
  onScheduleSaved: () => void
  /** 未保存改动确认：拦的是「关文档 / 换文件」 */
  doc: ReturnType<typeof useDocDirtyGuard>
}) {
  return (
    <>
      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={onPayClose}
        onSaved={onPaymentSaved}
      />

      <InvoicePoolDialog open={invoiceOpen} contractId={deal.id} onClose={onInvoiceClose} />

      <AddCaseDialog
        open={caseOpen}
        contractId={deal.id}
        stage={next ?? ''}
        stageCode={stageLabelsToCodes([next ?? ''])[0] ?? ''}
        caseType={deal.caseType}
        defaults={{ name: `${deal.client}·${next ?? ''}`, cause: '', amount: '', court: '' }}
        onClose={onCaseClose}
        onSaved={onCaseSaved}
      />

      <AddDeadlineDialog
        open={deadlineOpen}
        contractId={deal.id}
        cases={[]}
        onClose={onDeadlineClose}
        onSaved={onScheduleSaved}
      />

      <UnsavedChangesDialog open={doc.pending} onStay={doc.stay} onLeave={doc.leave} />
    </>
  )
}
