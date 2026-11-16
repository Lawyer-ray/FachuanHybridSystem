import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 到账待认领 API 层：前缀、端点形状与 default-arg 分支。
 *
 * 锁死接口前缀的**完整形态**。
 *
 * 曾经的真 bug：只写 `'/contracts/finance/intake'`，请求落到
 * `http://host/contracts/finance/intake/...`（缺 `/api/v1`）→ 404，
 * 首页「待认领款项」一直加载不出来，但 tsc/lint/单测全绿——因为
 * `createApiClient({prefix})` 的 prefix 会**整体覆盖** `/api/v1`
 * 而不是相对拼接，这是运行期才暴露的语义。
 *
 * 所以这里断言 prefix 必须以 `/api/v1/` 开头且是绝对路径。
 *
 * 端点与默认值部分守的是「不同动作不能串」：
 * - confirm 把 `contractId` 省略时 body 里必须是 `contract_id: null`（采纳
 *   系统建议），漏字段与显式 null 在后端不是同一件事；
 * - reject 与 ignore 是两个端点（非记账事件 / 不需记账），串了不会报错，
 *   只会让财务口径错一整类往来款；
 * - `listPendingIntakes(limit=20)` / `rescanIntakes(days=14)` 的默认值是
 *   default-arg 分支，改小了会让首页只显示一部分待办、补扫漏掉邮件。
 */
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
    // 方法返回可 `.json()` 的 thenable，且带一个可改写的 body 槽
    const recorder = {
      prefix,
      body: undefined as unknown,
      get: vi.fn(function (this: unknown) {
        return respond(recorder.body)
      }),
      post: vi.fn(function (this: unknown) {
        return respond(recorder.body)
      }),
    }
    recorders.push(recorder)
    return recorder
  },
}))

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

import * as api from './api'

const PREFIX = '/api/v1/contracts/finance/intake'

function intake(): Recorder {
  const r = recorders.find((x) => x.prefix === PREFIX)
  if (!r) throw new Error('intake 客户端未创建')
  return r
}

function lastPost() {
  const calls = intake().post.mock.calls
  return calls[calls.length - 1] as [string, Record<string, unknown>]
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('payment-intake api prefix', () => {
  it('必须带 /api/v1 前缀（createApiClient 的 prefix 是覆盖而非拼接）', async () => {
    await api.listPendingIntakes()
    expect(intake().prefix.startsWith('/api/v1/')).toBe(true)
    expect(intake().prefix).toBe(PREFIX)
  })
})

describe('payment-intake api：查询', () => {
  it('列表默认 limit=20，字符串化进 searchParams', async () => {
    await api.listPendingIntakes()
    // 默认值改小会让首页「待认领款项」只显示一部分，且没有任何提示
    expect(intake().get).toHaveBeenCalledWith('pending', { searchParams: { limit: '20' } })
  })

  it('显式 limit 覆盖默认值', async () => {
    await api.listPendingIntakes(5)
    expect(intake().get).toHaveBeenCalledWith('pending', { searchParams: { limit: '5' } })
  })

  it('角标只把 count 字段透给调用方', async () => {
    ;(intake() as unknown as { body: unknown }).body = { count: 6 }
    await expect(api.getPendingCount()).resolves.toBe(6)
    ;(intake() as unknown as { body: unknown }).body = undefined
  })

  it('详情按 id 拼路径', async () => {
    await api.getIntake(9)
    expect(intake().get).toHaveBeenCalledWith('9')
  })

  it('下拉搜索默认「无关键字 + 50 条」（与自动匹配共用资格规则）', async () => {
    await api.listSelectableContracts()
    expect(intake().get).toHaveBeenCalledWith('selectable-contracts', {
      searchParams: { search: '', limit: '50' },
    })
  })
})

describe('payment-intake api：裁定端点不能串', () => {
  it('confirm 不传 contractId 时 body 里是 contract_id: null（采纳系统建议）', async () => {
    await api.confirmIntake(9)
    const [path, opts] = lastPost()
    expect(path).toBe('9/confirm')
    expect(opts.json).toEqual({ contract_id: null, note: '' })
  })

  it('confirm 传了 contractId 与 note 时原样透传', async () => {
    await api.confirmIntake(9, 11, '按判决书归属')
    expect(lastPost()[1].json).toEqual({ contract_id: 11, note: '按判决书归属' })
  })

  it('reject 打 reject 端点（标记为非记账事件）', async () => {
    await api.rejectIntake(9, '不是本案款项')
    const [path, opts] = lastPost()
    expect(path).toBe('9/reject')
    expect(opts.json).toEqual({ reason: '不是本案款项' })
  })

  it('ignore 打 ignore 端点（不需记账：往来款/退款）——与 reject 是两个动作', async () => {
    await api.ignoreIntake(9, '客户退款往来')
    const [path, opts] = lastPost()
    // 串成 reject 不会报错，只是这类款项从此被归进「非记账事件」，
    // 财务对账时才发现口径错了
    expect(path).toBe('9/ignore')
    expect(opts.json).toEqual({ reason: '客户退款往来' })
  })

  it('reopen 只按 id、无 body（会同时删掉已生成的收款记录）', async () => {
    await api.reopenIntake(9)
    expect(lastPost()[0]).toBe('9/reopen')
  })

  it('rescan 默认 days=14，走 searchParams', async () => {
    await api.rescanIntakes()
    expect(lastPost()[0]).toBe('rescan')
    expect(lastPost()[1].searchParams).toEqual({ days: '14' })
  })

  it('rescan 显式 days 覆盖默认值', async () => {
    await api.rescanIntakes(30)
    expect(lastPost()[1].searchParams).toEqual({ days: '30' })
  })
})
