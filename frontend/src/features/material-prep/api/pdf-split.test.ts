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

import { findInflightPdfSplitJob, findReusablePdfSplitJob, jobDownloadUrl, segmentMdUrl, segmentPdfUrl } from './pdf-split'

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

/**
 * 下载直链构造函数。
 *
 * 三个函数返回的是**给人手动打开会 401 的裸地址**，唯一合法用法是交给
 * `withDownloadTicket()` 换一次性票据后再打开（安全审计 M-2，见函数注释与
 * `inbox/components/InboxView.dom.test.tsx` 里那次 401 事故的回归注释）。
 * 因此这里锁两件事：
 *  1. 前缀与资源路径逐字正确（后端 router 挂在 `/pdf-splitting` 下，不猜）；
 *  2. `?ids=` 只出现在选中集非空时，且拼的是 segment 主键。
 */
describe('下载直链：单段 PDF / 单段 MD / 整包（含 ?ids=）', () => {
  it('单段 PDF：路径与后端 /pdf-splitting/jobs/{job_id}/segments/{id}/pdf 一致', () => {
    expect(segmentPdfUrl('job-7', 12)).toBe('/api/v1/pdf-splitting/jobs/job-7/segments/12/pdf')
  })

  it('单段 MD：与 PDF 同一前缀、同一主键，只有末段不同', () => {
    expect(segmentMdUrl('job-7', 12)).toBe('/api/v1/pdf-splitting/jobs/job-7/segments/12/md')
  })

  it('整包下载不带 query（后端按整个任务打包）', () => {
    expect(jobDownloadUrl('job-7')).toBe('/api/v1/pdf-splitting/jobs/job-7/download')
    expect(jobDownloadUrl('job-7', [])).toBe('/api/v1/pdf-splitting/jobs/job-7/download')
  })

  it('只打选中段：ids 为逗号分隔的 segment 主键，且排序去重（同一组选择→同一 URL）', () => {
    expect(jobDownloadUrl('job-7', [15, 12, 15])).toBe('/api/v1/pdf-splitting/jobs/job-7/download?ids=12,15')
  })

  it('非正整数的主键被丢掉：传错只会让后端 400，不如在拼串时就清掉', () => {
    expect(jobDownloadUrl('job-7', [12, 0, -3, 1.5, Number.NaN])).toBe(
      '/api/v1/pdf-splitting/jobs/job-7/download?ids=12',
    )
    // 全是脏值等于什么都没选中 → 退回整包路径（绝不拼出 ?ids= 这种空参）
    expect(jobDownloadUrl('job-7', [0, -1])).toBe('/api/v1/pdf-splitting/jobs/job-7/download')
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
