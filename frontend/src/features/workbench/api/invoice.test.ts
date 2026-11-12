/**
 * workbench/api/invoice 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient（contracts 客户端）；断言聚焦
 * 路径 / 查询参数 / multipart 字段与超时，以及 copyInvoiceToClipboard 对
 * 「业务错误包装成 HTTP 200」的拆包口径。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const client = {
      prefix: opts?.prefix ?? '/api/v1',
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    }
    clients.push(client)
    return client
  },
}))

import {
  attachPaymentInvoice,
  contractInvoiceKeys,
  copyInvoiceToClipboard,
  deletePaymentInvoice,
  detachPaymentInvoice,
  listContractInvoices,
  listContractPayments,
  listPaymentInvoices,
  parsePaymentImage,
  parsePaymentText,
  uploadContractInvoices,
  uploadPaymentInvoices,
} from './invoice'

function contractsClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/contracts')
  if (!c) throw new Error('contracts 客户端未创建')
  return c
}

/** ky 链桩：返回可 `.json()` 的 Promise */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function file(name: string) {
  return new File(['x'], name, { type: 'application/pdf' })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('识别草稿（只解析不落库）', () => {
  it('parsePaymentText POST 短信正文', async () => {
    const draft = { amount: '100.00', payer: '张三', hints: [] }
    contractsClient().post.mockReturnValue(respond(draft))
    await expect(parsePaymentText('到账 100 元')).resolves.toEqual(draft)
    const [path, opts] = contractsClient().post.mock.calls[0]!
    expect(path).toBe('finance/payments/parse-text')
    expect(opts.json).toEqual({ text: '到账 100 元' })
  })

  it('parsePaymentImage 用 multipart 传 file 字段并放宽超时', async () => {
    contractsClient().post.mockReturnValue(respond({ is_receipt: true }))
    await expect(parsePaymentImage(file('回单.png'))).resolves.toEqual({ is_receipt: true })
    const [path, opts] = contractsClient().post.mock.calls[0]!
    expect(path).toBe('finance/payments/parse-image')
    expect(opts.timeout).toBe(300_000)
    const form = opts.body as FormData
    expect(form).toBeInstanceOf(FormData)
    expect((form.get('file') as File).name).toBe('回单.png')
  })
})

describe('收款下发票', () => {
  it('listPaymentInvoices 带上 contract_id 参与行级鉴权', async () => {
    contractsClient().get.mockReturnValue(respond([]))
    await listPaymentInvoices(7, 9)
    const [path, opts] = contractsClient().get.mock.calls[0]!
    expect(path).toBe('finance/payments/7/invoices')
    expect(opts.searchParams).toEqual({ contract_id: '9' })
  })

  it('uploadPaymentInvoices 一次 multipart 传多张（字段名 files）', async () => {
    contractsClient().post.mockReturnValue(respond({ saved: [], failed: [] }))
    await uploadPaymentInvoices(7, [file('a.pdf'), file('b.pdf')])
    const [path, opts] = contractsClient().post.mock.calls[0]!
    expect(path).toBe('finance/payments/7/invoices')
    const form = opts.body as FormData
    expect(form.getAll('files').map((f) => (f as File).name)).toEqual(['a.pdf', 'b.pdf'])
    expect(opts.timeout).toBe(300_000)
  })

  it('deletePaymentInvoice DELETE finance/invoices/{id}', async () => {
    contractsClient().delete.mockReturnValue(respond({ success: true }))
    await expect(deletePaymentInvoice(3)).resolves.toEqual({ success: true })
    expect(contractsClient().delete).toHaveBeenCalledWith('finance/invoices/3')
  })
})

describe('合同名下发票（先开票后付款）', () => {
  it('listContractInvoices 默认不带 unlinked', async () => {
    contractsClient().get.mockReturnValue(respond([]))
    await listContractInvoices(9)
    expect(contractsClient().get.mock.calls[0]).toEqual(['finance/contracts/9/invoices', { searchParams: {} }])
  })

  it('unlinked=true 时带 unlinked 查询参数', async () => {
    contractsClient().get.mockReturnValue(respond([]))
    await listContractInvoices(9, true)
    expect(contractsClient().get.mock.calls[0]).toEqual([
      'finance/contracts/9/invoices',
      { searchParams: { unlinked: 'true' } },
    ])
  })

  it('uploadContractInvoices 传到合同名下', async () => {
    contractsClient().post.mockReturnValue(respond({ saved: [], failed: [] }))
    await uploadContractInvoices(9, [file('a.pdf')])
    const [path, opts] = contractsClient().post.mock.calls[0]!
    expect(path).toBe('finance/contracts/9/invoices')
    expect((opts.body as FormData).getAll('files')).toHaveLength(1)
  })

  it('listContractPayments 按 contract_id 拉收款简报', async () => {
    contractsClient().get.mockReturnValue(respond([{ id: 1, amount: '100.00' }]))
    await listContractPayments(9)
    expect(contractsClient().get.mock.calls[0]).toEqual([
      'finance/payments',
      { searchParams: { contract_id: '9' } },
    ])
  })

  it('contractInvoiceKeys 生成互不冲突的缓存 key', () => {
    expect(contractInvoiceKeys.all(9)).toEqual(['contract-invoices', 9])
    expect(contractInvoiceKeys.unlinked(9)).toEqual(['contract-invoices', 9, 'unlinked'])
    expect(contractInvoiceKeys.all(9)).not.toEqual(contractInvoiceKeys.all(10))
  })
})

describe('发票 ↔ 收款关联', () => {
  it('attachPaymentInvoice POST invoice_id/attach + payment_id', async () => {
    contractsClient().post.mockReturnValue(respond({ invoice: { id: 1 }, invoice_status: 'ok' }))
    await attachPaymentInvoice(1, 7)
    const [path, opts] = contractsClient().post.mock.calls[0]!
    expect(path).toBe('finance/invoices/1/attach')
    expect(opts.json).toEqual({ payment_id: 7 })
  })

  it('detachPaymentInvoice POST invoice_id/detach（无 body）', async () => {
    contractsClient().post.mockReturnValue(respond({ invoice: { id: 1 } }))
    await detachPaymentInvoice(1)
    expect(contractsClient().post.mock.calls[0]).toEqual(['finance/invoices/1/detach'])
  })
})

describe('copyInvoiceToClipboard：拆业务包装', () => {
  it('success=true 时返回 copied 与 reason', async () => {
    contractsClient().post.mockReturnValue(respond({ success: true, copied: 1, reason: null }))
    await expect(copyInvoiceToClipboard(1)).resolves.toEqual({ success: true, copied: 1, reason: null })
    expect(contractsClient().post.mock.calls[0]).toEqual(['finance/invoices/1/copy-to-clipboard'])
  })

  it('success=false + reason=unsupported 原样返回（调用方降级复制文件名）', async () => {
    contractsClient().post.mockReturnValue(respond({ success: false, reason: 'unsupported' }))
    await expect(copyInvoiceToClipboard(1)).resolves.toEqual({ success: false, copied: 0, reason: 'unsupported' })
  })

  it('success 缺失但有 message 时抛错（业务失败伪装成 200）', async () => {
    contractsClient().post.mockReturnValue(respond({ message: '文件不存在' }))
    await expect(copyInvoiceToClipboard(1)).rejects.toThrow('文件不存在')
  })

  it('success 缺失且无 message 时按失败返回', async () => {
    contractsClient().post.mockReturnValue(respond({}))
    await expect(copyInvoiceToClipboard(1)).resolves.toEqual({ success: false, copied: 0, reason: null })
  })
})
