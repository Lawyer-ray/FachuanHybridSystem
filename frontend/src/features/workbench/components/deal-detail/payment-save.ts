/**
 * 收款保存：创建 `ContractPayment` 并回读它名下的发票。
 *
 * 独立成模块（而非内联进弹窗）有两个原因：
 * 1. 先建收款、再挂发票是**两步**，弹窗里要拿到 `id` 才能解禁发票区；
 * 2. 业务错误是 HTTP 200 + `{success:false, message}` 的既有约定，必须在
 *    mutation 内 throw 才走得到 `onError`（见 frontend/CLAUDE.md）。
 */

import { createApiClient } from '@/lib/api'

import { toCreatePayload, type PaymentForm } from './payment-form'
import type { PaymentInvoice } from '../../api'

const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })

interface PaymentCreated {
  id: number
  invoices: PaymentInvoice[]
}

/** 创建收款（confirm=true：弹窗本身即确认动作），随后取该收款的发票（新建时通常为空） */
export async function savePayment(contractId: number, form: PaymentForm): Promise<PaymentCreated> {
  const payload = toCreatePayload(contractId, form)
  const created = await contractsApi.post('finance/payments', { json: payload }).json<{ id: number }>()
  if (!created?.id) {
    throw new Error('收款已提交但未返回记录 id，请刷新页面确认')
  }

  const invoices = await contractsApi
    .get(`finance/payments/${created.id}/invoices`, { searchParams: { contract_id: String(contractId) } })
    .json<PaymentInvoice[]>()
    .catch(() => [])

  return { id: created.id, invoices }
}
