/**
 * 发票待认领（Invoice Intake）的对外出口。
 *
 * 其它 feature / app 层**只从这里引**，不穿透内部目录（api.ts / hooks / components）。
 * 首页（features/home）单向引用本出口的 PendingInvoicesCard；本 feature 不得
 * 反向 import features/home 的内部文件，同样禁止 import features/payment-intake
 * 的任何内部文件（feature 之间禁止互相 import，见 frontend/CLAUDE.md）。
 */
export { PendingInvoicesCard } from './components/PendingInvoicesCard'
export { InvoiceIntakeRow } from './components/InvoiceIntakeRow'
export type {
  InvoiceActionResult,
  InvoiceCandidate,
  InvoiceIntake,
  InvoiceIntakeStatus,
  InvoiceMatchKind,
  InvoicePaymentOption,
  PaymentPickConfidence,
  SelectableContract,
} from './types'
export { INVOICE_INTAKE_COUNT_KEY, INVOICE_INTAKE_PENDING_KEY, INVOICE_SELECTABLE_KEY } from './api'
