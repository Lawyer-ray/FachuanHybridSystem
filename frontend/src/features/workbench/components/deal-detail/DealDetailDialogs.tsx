import { DraftDialog } from '@/features/doc-generation'

import { stageLabelsToCodes } from '../../contract-enums'
import type { DealCase, WorkbenchDeal } from '../../types'
import { AddCaseDialog } from './AddCaseDialog'
import { AddDeadlineDialog } from './AddDeadlineDialog'
import { AddLogDialog } from './AddLogDialog'
import { InvoicePoolDialog } from './InvoicePoolDialog'
import { PaymentDialog } from './PaymentDialog'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import type { useDocDirtyGuard } from './use-doc-dirty-guard'
import type { useDraftDialog } from './use-draft-dialog'

/**
 * 诉讼详情页挂在页面底部的弹窗：记收款 / 发票池 / 新建下一程序案件 / 记日志 /
 * 新增期限 / 未保存改动确认 / 一句话生成文书。
 *
 * 抽出来的判据是关注点边界：这些弹窗只由页面状态开合、保存后回刷页面数据，
 * 与左栏案件链、右栏档案卡的渲染无关。**状态、滚动高亮与刷新口径仍归页面**
 * （`payOpen` / `caseOpen` / `logTarget` / `newCaseId`、`onScheduleChanged` /
 * `onMoneyChanged` 等），本组件只做接线，所以没有自己的 useState。
 */
export function DealDetailDialogs({
  contractId,
  deal,
  ordered,
  next,
  defaultCaseName,
  payOpen,
  onPayClose,
  onPaymentSaved,
  invoiceOpen,
  onInvoiceClose,
  caseOpen,
  onCaseClose,
  onCaseSaved,
  logTarget,
  onLogClose,
  onScheduleSaved,
  deadlineOpen,
  onDeadlineClose,
  doc,
  draft,
}: {
  contractId: number
  deal: WorkbenchDeal
  /** 按程序序排好的案件：建案默认值取上一程，期限弹窗挑案件也用它 */
  ordered: DealCase[]
  /** 合同勾选的下一程序（建案弹窗的阶段固定为它） */
  next: string | null
  /** 新案件默认名（页面的「甲诉乙+案由」口径，见 DealDetailPage） */
  defaultCaseName: string
  payOpen: boolean
  onPayClose: () => void
  /** 记收款保存后刷新合同 + 案件 + 工作台列表（与「关联发票」同一口径） */
  onPaymentSaved: () => void
  invoiceOpen: boolean
  onInvoiceClose: () => void
  caseOpen: boolean
  onCaseClose: () => void
  /** 建案保存：页面刷新合同+案件，并记下新 id 等列表出现后滚过去 */
  onCaseSaved: (caseId: number) => void
  /** 正在记日志的案件（null = 弹窗关闭）；日志归属具体案件，所以带 id + 程序名 */
  logTarget: { id: number; label: string } | null
  onLogClose: () => void
  /** 期限/日志写完后刷新合同 + 案件 + 案件直挂提醒 */
  onScheduleSaved: () => void
  deadlineOpen: boolean
  onDeadlineClose: () => void
  /** 未保存改动确认：拦的是「关文档 / 换文件」，不是页面级导航 */
  doc: ReturnType<typeof useDocDirtyGuard>
  /** 起草弹窗的状态编排（页面用 useDraftDialog 持有，成稿落回本页画布） */
  draft: ReturnType<typeof useDraftDialog>
}) {
  return (
    <>
      {/* 记收款：粘贴到账短信 / 拖发票。保存后刷新合同，右栏收费节即时更新 */}
      <PaymentDialog
        open={payOpen}
        contractId={deal.id}
        fixedAmount={deal.amountNum}
        receivedAmount={Number(deal.totalReceived?.replace(/[^\d.]/g, '') || 0)}
        onClose={onPayClose}
        // 与「关联发票」同一口径：合同 + 案件 + 工作台列表一起刷。
        // 只 refetch 本页的话，退回列表 60s 内还是旧金额（staleTime），
        // 看起来像「记了收款但没记上」。
        onSaved={onPaymentSaved}
      />

      {/* 先开票后付款：票挂合同名下；关闭即失效未关联缓存，右栏计数同步 */}
      <InvoicePoolDialog open={invoiceOpen} contractId={deal.id} onClose={onInvoiceClose} />

      {/* 新建下一程序案件：阶段固定为合同勾选、尚未立案的那个程序 */}
      <AddCaseDialog
        open={caseOpen}
        contractId={contractId}
        stage={next ?? ''}
        stageCode={stageLabelsToCodes([next ?? ''])[0] ?? ''}
        caseType={deal.caseType}
        defaults={{
          name: defaultCaseName,
          cause: ordered.at(-1)?.cause ?? '',
          amount: deal.amountNum != null ? String(deal.amountNum) : '',
          court: ordered.at(-1)?.auth ?? '',
        }}
        onClose={onCaseClose}
        onSaved={onCaseSaved}
      />

      {/* 记日志：归属就是点它的那张案件卡；「同时设期限」走同一次请求 */}
      <AddLogDialog
        open={logTarget !== null}
        caseId={logTarget?.id ?? 0}
        caseLabel={logTarget?.label ?? ''}
        onClose={onLogClose}
        onSaved={onScheduleSaved}
      />

      {/* 新增期限：默认挂整个委托，也可以挑某个案件 */}
      <AddDeadlineDialog
        open={deadlineOpen}
        contractId={contractId}
        cases={ordered.map((c) => ({ id: c.id, proc: c.proc }))}
        onClose={onDeadlineClose}
        onSaved={onScheduleSaved}
      />

      <UnsavedChangesDialog open={doc.pending} onStay={doc.stay} onLeave={doc.leave} />

      {/* 一句话生成文书。只有诉讼分支挂它：已上线的 spec 都是案件文书，合同文件夹
          模板里没有对应落位节点（传 contract 侧会得到 created=false + 原因） */}
      <DraftDialog
        open={draft.caseId != null}
        onOpenChange={(v) => {
          if (!v) draft.close()
        }}
        caseId={draft.caseId}
        onCreated={draft.onCreated}
      />
    </>
  )
}
