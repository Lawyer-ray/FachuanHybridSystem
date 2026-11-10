import { describe, expect, it, vi } from 'vitest'

/**
 * 锁死接口前缀的**完整形态**。
 *
 * 曾经的真 bug：只写 `'/contracts/finance/intake'`，请求落到
 * `http://host/contracts/finance/intake/...`（缺 `/api/v1`）→ 404，
 * 首页「待认领款项」一直加载不出来，但 tsc/lint/单测全绿——因为
 * `createApiClient({prefix})` 的 prefix 会**整体覆盖** `/api/v1`
 * 而不是相对拼接，这是运行期才暴露的语义。
 *
 * 所以这里断言 prefix 必须以 `/api/v1/` 开头且是绝对路径。
 */
const captured: { prefix?: string }[] = []

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    captured.push(opts ?? {})
    return { get: vi.fn(), post: vi.fn() }
  },
}))

describe('payment-intake api prefix', () => {
  it('必须带 /api/v1 前缀（createApiClient 的 prefix 是覆盖而非拼接）', async () => {
    await import('./api')
    expect(captured.length).toBeGreaterThan(0)
    const prefix = captured[0]?.prefix ?? ''
    expect(prefix.startsWith('/api/v1/')).toBe(true)
    expect(prefix).toBe('/api/v1/contracts/finance/intake')
  })
})
