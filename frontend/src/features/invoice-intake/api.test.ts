/**
 * 发票待认领 API 层的路径与默认值锁定（node 环境）。
 *
 * 三件事必须锁死，因为它们的错法都不会报错：
 *
 * 1. **两个 prefix**。发票主流程挂在 `/api/v1/contracts/finance/invoice-intake`，
 *    但「复制重命名后的发票文件」复用的是项目详情页既有的
 *    `/api/v1/contracts/finance/invoices/{id}/copy-to-clipboard`。它们**不是**
 *    同一前缀——按 invoice-intake 前缀去拼 `invoices/1/copy-to-clipboard` 会
 *    404，而按钮只是「点了没反应」。
 * 2. **确认时不传的归属要显式写成 null**。`confirmInvoiceIntake(id)` 的 body
 *    必须是 `{contract_id: null, payment_id: null}`（= 采纳系统建议），漏字段
 *    与传 null 在后端是不同的语义（缺字段可能被当成空补丁）。
 * 3. **默认值分支**。`confirmRedReenact` 的 `note=''` / `amountOverride=false`
 *    各是一个 default-arg 分支，红票「金额不覆盖」是财务口径上的默认安全值，
 *    被悄悄改成 true 就等于允许红票与原票金额不等。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Recorder = {
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const recorders = vi.hoisted(() => [] as Recorder[])

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = recorders.find((r) => r.prefix === prefix)
    if (existing) return existing
    const respond = () => {
      const p = Promise.resolve({})
      return Object.assign(p, { json: () => p })
    }
    const recorder: Recorder = { prefix, get: vi.fn(() => respond()), post: vi.fn(() => respond()) }
    recorders.push(recorder)
    return recorder
  },
}))

import * as api from './api'

function clientOf(prefix: string): Recorder {
  const r = recorders.find((x) => x.prefix === prefix)
  if (!r) throw new Error(`${prefix} 客户端未创建`)
  return r
}

const INTAKE_PREFIX = '/api/v1/contracts/finance/invoice-intake'
const FINANCE_PREFIX = '/api/v1/contracts/finance'

function intake() {
  return clientOf(INTAKE_PREFIX)
}

function lastIntakePost() {
  const calls = intake().post.mock.calls
  return calls[calls.length - 1] as [string, Record<string, unknown>]
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('invoice-intake api：prefix', () => {
  it('主流程走 /api/v1/contracts/finance/invoice-intake（覆盖语义，必须带 /api/v1）', async () => {
    await api.listPendingInvoices()
    expect(intake().prefix).toBe(INTAKE_PREFIX)
  })

  it('复制发票走 /contracts/finance 而不是 intake 前缀（复用项目详情页既有端点）', async () => {
    await api.copyInvoiceToClipboard(42)
    // 前缀错一位就会 404，表现为「点了复制没反应」
    const [path] = clientOf(FINANCE_PREFIX).post.mock.calls[0] as [string]
    expect(path).toBe('invoices/42/copy-to-clipboard')
    expect(intake().post).not.toHaveBeenCalled()
  })
})

describe('invoice-intake api：查询', () => {
  it('列表带 limit（默认 20，字符串化）', async () => {
    await api.listPendingInvoices()
    expect(intake().get).toHaveBeenCalledWith('pending', { searchParams: { limit: '20' } })
  })

  it('角标只取 count 字段，不把整个对象透给调用方', async () => {
    intake().get.mockReturnValueOnce(
      Object.assign(Promise.resolve({ count: 4 }), { json: () => Promise.resolve({ count: 4 }) }),
    )
    await expect(api.getPendingInvoiceCount()).resolves.toBe(4)
  })

  it('详情按 id 拼路径（数字转字符串）', async () => {
    await api.getInvoiceIntake(7)
    expect(intake().get).toHaveBeenCalledWith('7')
  })

  it('下拉搜索的默认值是「无关键字 + 50 条」（后端不做空关键字过滤，靠 limit 收窄）', async () => {
    await api.listSelectableContracts()
    expect(intake().get).toHaveBeenCalledWith('selectable-contracts', {
      searchParams: { search: '', limit: '50' },
    })
  })
})

describe('invoice-intake api：确认与裁定', () => {
  it('不传归属时 body 显式写成 null（采纳系统建议，而不是漏字段）', async () => {
    await api.confirmInvoiceIntake(7)
    expect(lastIntakePost()[1].json).toEqual({ contract_id: null, payment_id: null })
  })

  it('只传 contractId 时 payment_id 仍显式为 null（不传 ≠ 空字符串）', async () => {
    await api.confirmInvoiceIntake(7, 11)
    expect(lastIntakePost()[1].json).toEqual({ contract_id: 11, payment_id: null })
  })

  it('reject 带 reason，打 reject 端点', async () => {
    await api.rejectInvoiceIntake(7, '非本项目发票')
    const [path, opts] = lastIntakePost()
    expect(path).toBe('7/reject')
    expect(opts.json).toEqual({ reason: '非本项目发票' })
  })

  it('reopen 只按 id，无 body', async () => {
    await api.reopenInvoiceIntake(7)
    expect(lastIntakePost()[0]).toBe('7/reopen')
  })

  it('reparse 只按 id（红票金额未识别时的唯一正解）', async () => {
    await api.reparseIntake(7)
    expect(lastIntakePost()[0]).toBe('7/reparse')
  })
})

describe('invoice-intake api：红票三个入口的默认值与端点', () => {
  it('confirmRedReenact 不传 note/amountOverride 时用默认值（空串 / false）', async () => {
    await api.confirmRedReenact(7, 30)
    const [path, opts] = lastIntakePost()
    expect(path).toBe('7/confirm-red-reenact')
    // amount_override 默认 false 是财务安全值：允许红票金额与原票不等
    // 必须由律师显式确认
    expect(opts.json).toEqual({ new_intake_id: 30, note: '', amount_override: false })
  })

  it('confirmRedReenact 接受 newIntakeId 为 null（组内没有蓝票可重开）', async () => {
    await api.confirmRedReenact(7, null, '差额已核', true)
    expect(lastIntakePost()[1].json).toEqual({ new_intake_id: null, note: '差额已核', amount_override: true })
  })

  it('confirmRedOnly 的 note 默认空串，且打的是 confirm-red-only（不重开）', async () => {
    await api.confirmRedOnly(7)
    const [path, opts] = lastIntakePost()
    expect(path).toBe('7/confirm-red-only')
    expect(opts.json).toEqual({ note: '' })
  })
})

describe('invoice-intake api：补扫', () => {
  it('rescanInvoiceIntakes 默认 days=14，走 searchParams', async () => {
    await api.rescanInvoiceIntakes()
    expect(lastIntakePost()[0]).toBe('rescan')
    expect(lastIntakePost()[1].searchParams).toEqual({ days: '14' })
  })

  it('显式 days 覆盖默认值', async () => {
    await api.rescanInvoiceIntakes(3)
    expect(lastIntakePost()[1].searchParams).toEqual({ days: '3' })
  })
})
