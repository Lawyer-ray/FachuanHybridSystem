/**
 * payment-save：创建收款后回读发票（node 环境）。
 *
 * 两步是必须的：先建 `ContractPayment` 拿到 id，弹窗才能解禁发票区；
 * 业务错误走 HTTP 200 + `{success:false}` 的既有约定，所以「没返回 id」必须在
 * 这里 throw 才走得到 mutation 的 onError。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: () => client,
}))

import { EMPTY_FORM } from './payment-form'
import { savePayment } from './payment-save'

/** ky 链桩：`client.get(...).json()`；`.catch` 由 Promise 自身提供 */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

const FORM = { ...EMPTY_FORM, amount: '12,345.60', receivedAt: '2026-10-20', note: ' 首付款 ' }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('savePayment', () => {
  it('POST 收款后再 GET 该收款的发票，返回 id + invoices', async () => {
    client.post.mockReturnValue(respond({ id: 77 }))
    const invoices = [{ id: 1, invoice_number: '0001' }]
    client.get.mockReturnValue(respond(invoices))

    const out = await savePayment(9, FORM)

    expect(out).toEqual({ id: 77, invoices })
    const [postPath, postOpts] = client.post.mock.calls[0]!
    expect(postPath).toBe('finance/payments')
    expect(postOpts.json).toMatchObject({
      contract_id: 9,
      amount: 12345.6,
      received_at: '2026-10-20',
      note: '首付款',
      confirm: true,
    })
    const [getPath, getOpts] = client.get.mock.calls[0]!
    expect(getPath).toBe('finance/payments/77/invoices')
    expect(getOpts.searchParams).toEqual({ contract_id: '9' })
  })

  it('后端没返回 id 时抛错（业务错误不让它静默成功）', async () => {
    client.post.mockReturnValue(respond({ success: false, message: '余额不足' }))
    await expect(savePayment(9, FORM)).rejects.toThrow('收款已提交但未返回记录 id，请刷新页面确认')
    expect(client.get).not.toHaveBeenCalled()
  })

  it('id 为 0 也视为未返回', async () => {
    client.post.mockReturnValue(respond({ id: 0 }))
    await expect(savePayment(9, FORM)).rejects.toThrow()
  })

  it('发票回读失败降级成空数组（不拖垮「收款已建成」）', async () => {
    client.post.mockReturnValue(respond({ id: 77 }))
    const failing = Promise.reject(new Error('500'))
    client.get.mockReturnValue(Object.assign(failing, { json: () => failing }))

    await expect(savePayment(9, FORM)).resolves.toEqual({ id: 77, invoices: [] })
  })
})
