import { UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

import { contractsApi } from './client'

/* ============ 记收款：到账短信识别 + 发票拖拽（后端 contractpayment_enhance_api） ============ */

/** 到账短信解析草稿：识别不出的字段为空，由表单让人补 */
export interface PaymentParseDraft {
  amount: string | null
  received_at: string | null
  payer: string
  note: string
  hints: string[]
}

/** 发票（GET/POST 同一个投影）。payment_id 为 null = 先开票后付款，挂在合同名下、尚未归属某笔收款 */
export interface PaymentInvoice {
  id: number
  payment_id: number | null
  original_filename: string
  display_filename: string
  file_url: string
  invoice_code: string
  invoice_number: string
  invoice_date: string | null
  amount: string | null
  tax_amount: string | null
  total_amount: string | null
  seller_name: string
  buyer_name: string
  uploaded_at: string
}

/** 批量上传结果：成功逐张返回，失败逐张带原因 */
export interface InvoiceUploadResult {
  saved: PaymentInvoice[]
  failed: Array<{ filename: string; reason: string }>
  invoice_status: string
  invoice_status_label: string
  invoiced_amount: string
  duplicated_count: number
}

/** 粘贴的到账短信/截图文字 → 收款草稿（只解析，不落库） */
export async function parsePaymentText(text: string): Promise<PaymentParseDraft> {
  return contractsApi.post('finance/payments/parse-text', { json: { text } }).json<PaymentParseDraft>()
}

/** 某条收款下的发票列表（contract_id 参与行级鉴权，必须传） */
export async function listPaymentInvoices(paymentId: number, contractId: number): Promise<PaymentInvoice[]> {
  return contractsApi
    .get(`finance/payments/${paymentId}/invoices`, { searchParams: { contract_id: String(contractId) } })
    .json<PaymentInvoice[]>()
}

/**
 * 拖进来的发票：逐张识别 + 落盘 + 回填开票金额。
 *
 * 一次 multipart 传多张，后端逐张独立成败（一张坏文件不拖垮整批），
 * 所以错误处理在返回值里而不在 catch 里。
 */
export async function uploadPaymentInvoices(paymentId: number, files: File[]): Promise<InvoiceUploadResult> {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return contractsApi
    .post(`finance/payments/${paymentId}/invoices`, { body: form, timeout: UPLOAD_TIMEOUT_MS })
    .json<InvoiceUploadResult>()
}

/** 删除发票（media 文件同删，开票金额由后端重算） */
export async function deletePaymentInvoice(invoiceId: number): Promise<{ success: boolean }> {
  return contractsApi.delete(`finance/invoices/${invoiceId}`).json<{ success: boolean }>()
}

/** 合同发票缓存 key（右栏未归属计数 / 记收款弹窗的池列表共用，上传/关联后按此失效） */
export const contractInvoiceKeys = {
  all: (contractId: number) => ['contract-invoices', contractId] as const,
  unlinked: (contractId: number) => ['contract-invoices', contractId, 'unlinked'] as const,
}

/** 合同发票列表：已归属收款的 + 先开票挂合同的；unlinked 只看尚未归属收款的 */
export async function listContractInvoices(contractId: number, unlinked = false): Promise<PaymentInvoice[]> {
  return contractsApi
    .get(`finance/contracts/${contractId}/invoices`, {
      searchParams: unlinked ? { unlinked: 'true' } : {},
    })
    .json<PaymentInvoice[]>()
}

/** 先开票后付款：票传到合同名下（不动开票金额），钱到账记完收款再 attach */
export async function uploadContractInvoices(contractId: number, files: File[]): Promise<InvoiceUploadResult> {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return contractsApi
    .post(`finance/contracts/${contractId}/invoices`, { body: form, timeout: UPLOAD_TIMEOUT_MS })
    .json<InvoiceUploadResult>()
}

/** 把合同挂靠发票关联到一笔收款（返回该收款最新开票状态，就地刷新用） */
export async function attachPaymentInvoice(
  invoiceId: number,
  paymentId: number,
): Promise<{ invoice: PaymentInvoice; invoice_status: string; invoice_status_label: string; invoiced_amount: string }> {
  return contractsApi
    .post(`finance/invoices/${invoiceId}/attach`, { json: { payment_id: paymentId } })
    .json<{ invoice: PaymentInvoice; invoice_status: string; invoice_status_label: string; invoiced_amount: string }>()
}

/**
 * 复制**重命名后**的发票文件到系统剪贴板（后端 NSPasteboard 落板，同 Finder ⌘C）。
 *
 * 微信对话框直接 ⌘V 粘出文件本体。后端非 macOS / 无 pyobjc 时 success=false
 * 且 reason=unsupported，调用方降级复制文件名（口径同法院短信文书）。
 */
export async function copyInvoiceToClipboard(
  invoiceId: number,
): Promise<{ success: boolean; copied: number; reason: string | null }> {
  const res = await contractsApi
    .post(`finance/invoices/${invoiceId}/copy-to-clipboard`)
    .json<components['schemas']['InvoiceCopyOut'] & { message?: string }>()
  if (res.success === undefined && res.message) throw new Error(res.message)
  return { success: res.success === true, copied: Number(res.copied ?? 0), reason: res.reason ?? null }
}
