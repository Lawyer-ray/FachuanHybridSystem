/**
 * 云端拆分「查已有任务」两个端点的单测（node 环境）。
 *
 * 这两个函数都是**优化**，不是主流程：`findReusablePdfSplitJob` 命中能省掉一次
 * 5-10 分钟、几十元的云端识别；`findInflightPdfSplitJob` 命中能让刷新的页面接管
 * 正在跑的任务。正因为是优化，它们的失败语义只有一个正确选择：**返回 null，
 * 不抛**。抛出去会让「自动识别」按钮因一次附加查询的抖动直接报错，律师看到的
 * 结论会是「识别功能坏了」，而实际上任务压根没开始。
 *
 * 参数口径同样要守：`total_pages` 只在拿到**真实且为正**的页数时才传。
 * 页数是猜的（`pagesUnknown` 兜底 1 页）时传上去只会查出空集——白打一次请求，
 * 还永远接管不到。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{ prefix: string; get: ReturnType<typeof vi.fn> }>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = clients.find((c) => c.prefix === prefix)
    if (existing) return existing
    const client = { prefix, get: vi.fn() }
    clients.push(client)
    return client
  },
}))

import { findInflightPdfSplitJob, findReusablePdfSplitJob } from './pdf-split'

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

/** 失败桩：与 ky 一致，await 与 .json() 都抛（带 ky 的 HTTPError 语义即可） */
function fail(error: Error) {
  const p = Promise.reject(error)
  p.catch(() => {}) // 用例里必然 await / catch，这里只防未处理 rejection 噪音
  return Object.assign(p, { json: () => p })
}

function splittingClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/pdf-splitting')
  if (!c) throw new Error('pdf-splitting 客户端未创建')
  return c
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('findReusablePdfSplitJob：复用已算好的任务', () => {
  it('命中时返回任务载荷（调用方据此跳过重跑，省一次云端费用）', async () => {
    const payload = { job_id: 'job-7', status: 'completed', segments: [{ id: 's1' }] }
    splittingClient().get.mockReturnValue(respond(payload))
    await expect(findReusablePdfSplitJob('证据材料.pdf', 164)).resolves.toEqual(payload)
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { source_name: '证据材料.pdf', total_pages: 164 },
    })
  })

  it('页数为正才带 total_pages（三重匹配靠它排掉同名短文档）', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await findReusablePdfSplitJob('a.pdf', 1)
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { source_name: 'a.pdf', total_pages: 1 },
    })
  })

  it.each([
    ['未传', undefined],
    ['0', 0],
    ['负数', -3],
  ])('页数%s时不带 total_pages（猜出来的页数只会查出空集）', async (_label, pages) => {
    splittingClient().get.mockReturnValue(respond(null))
    await findReusablePdfSplitJob('a.pdf', pages)
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { source_name: 'a.pdf' },
    })
  })

  it('没有可复用任务时返回 null（调用方照常新建）', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await expect(findReusablePdfSplitJob('a.pdf', 3)).resolves.toBeNull()
  })

  it('查询失败返回 null 而不是抛错：查复用只是优化，失败不该阻断识别主流程', async () => {
    splittingClient().get.mockReturnValue(fail(new Error('503 Service Unavailable')))
    await expect(findReusablePdfSplitJob('a.pdf', 3)).resolves.toBeNull()
  })
})

describe('findInflightPdfSplitJob：查在飞任务（幽灵任务）', () => {
  /**
   * 与复用查询同一套失败语义：刷新页面时探测失败，最多是少一个进度条，
   * 不该让整个阅读器进入错误态。
   */
  it('命中时返回任务载荷，参数口径与复用查询一致', async () => {
    const payload = { job_id: 'job-8', status: 'processing' }
    splittingClient().get.mockReturnValue(respond(payload))
    await expect(findInflightPdfSplitJob('卷宗.pdf', 164)).resolves.toEqual(payload)
    expect(splittingClient().get).toHaveBeenCalledWith('inflight-job', {
      searchParams: { source_name: '卷宗.pdf', total_pages: 164 },
    })
  })

  it('页数缺省时不带 total_pages', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await findInflightPdfSplitJob('卷宗.pdf')
    expect(splittingClient().get).toHaveBeenCalledWith('inflight-job', {
      searchParams: { source_name: '卷宗.pdf' },
    })
  })

  it('查询失败返回 null 而不是抛错（网络抖动不该在阅读器里留下未捕获拒绝）', async () => {
    splittingClient().get.mockReturnValue(fail(new Error('Network request failed')))
    await expect(findInflightPdfSplitJob('卷宗.pdf', 164)).resolves.toBeNull()
  })
})
