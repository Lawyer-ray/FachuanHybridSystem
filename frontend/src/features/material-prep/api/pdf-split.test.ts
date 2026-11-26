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

const clients = vi.hoisted(
  () => [] as Array<{ prefix: string; get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }>,
)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = clients.find((c) => c.prefix === prefix)
    if (existing) return existing
    const client = { prefix, get: vi.fn(), post: vi.fn() }
    clients.push(client)
    return client
  },
}))

import {
  cancelPdfSplitJob,
  createPdfSplitJob,
  findInflightPdfSplitJob,
  findReusablePdfSplitJob,
  jobDownloadUrl,
  segmentMdUrl,
  segmentPdfUrl,
} from './pdf-split'

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
    await expect(
      findReusablePdfSplitJob({ packMessageId: 617, sourceName: '证据材料.pdf', totalPages: 164 }),
    ).resolves.toEqual(payload)
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { pack_message_id: 617, source_name: '证据材料.pdf', total_pages: 164 },
    })
  })

  it('包主键必发：少了它后端只能按「同名 + 同页数」匹配，而那两维不唯一', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await findReusablePdfSplitJob({ packMessageId: 601, sourceName: 'a.pdf', totalPages: 1 })
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { pack_message_id: 601, source_name: 'a.pdf', total_pages: 1 },
    })
  })

  it.each([
    ['未传', undefined],
    ['0', 0],
    ['负数', -3],
  ])('页数%s时不带 total_pages（猜出来的页数只会查出空集）', async (_label, pages) => {
    splittingClient().get.mockReturnValue(respond(null))
    await findReusablePdfSplitJob({ packMessageId: 601, sourceName: 'a.pdf', totalPages: pages })
    expect(splittingClient().get).toHaveBeenCalledWith('reusable-job', {
      searchParams: { pack_message_id: 601, source_name: 'a.pdf' },
    })
  })

  it('没有可复用任务时返回 null（调用方照常新建）', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await expect(
      findReusablePdfSplitJob({ packMessageId: 601, sourceName: 'a.pdf', totalPages: 3 }),
    ).resolves.toBeNull()
  })

  it('查询失败返回 null 而不是抛错：查复用只是优化，失败不该阻断识别主流程', async () => {
    splittingClient().get.mockReturnValue(fail(new Error('503 Service Unavailable')))
    await expect(
      findReusablePdfSplitJob({ packMessageId: 601, sourceName: 'a.pdf', totalPages: 3 }),
    ).resolves.toBeNull()
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
    await expect(
      findInflightPdfSplitJob({ packMessageId: 617, sourceName: '卷宗.pdf', totalPages: 164 }),
    ).resolves.toEqual(payload)
    expect(splittingClient().get).toHaveBeenCalledWith('inflight-job', {
      searchParams: { pack_message_id: 617, source_name: '卷宗.pdf', total_pages: 164 },
    })
  })

  it('包主键必发：只按「同名 + 同页数」查会把别的包的任务认成这个包的', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await findInflightPdfSplitJob({ packMessageId: 601, sourceName: '卷宗.pdf' })
    expect(splittingClient().get).toHaveBeenCalledWith('inflight-job', {
      searchParams: { pack_message_id: 601, source_name: '卷宗.pdf' },
    })
  })

  it('页数未知时不带 total_pages（猜出来的页数只会查出空集）', async () => {
    splittingClient().get.mockReturnValue(respond(null))
    await findInflightPdfSplitJob({ packMessageId: 601, sourceName: '卷宗.pdf', totalPages: 0 })
    expect(splittingClient().get).toHaveBeenCalledWith('inflight-job', {
      searchParams: { pack_message_id: 601, source_name: '卷宗.pdf' },
    })
  })

  it('查询失败返回 null 而不是抛错（网络抖动不该在阅读器里留下未捕获拒绝）', async () => {
    splittingClient().get.mockReturnValue(fail(new Error('Network request failed')))
    await expect(
      findInflightPdfSplitJob({ packMessageId: 617, sourceName: '卷宗.pdf', totalPages: 164 }),
    ).resolves.toBeNull()
  })
})

// ── 彻底停止：取消云端任务 ────────────────────────────────────
//
// 「不再显示」只收起浮条，任务照旧在云端跑（继续计费）。这是用户唯一能让
// 那个**跑错了的任务**真停下来的入口，所以请求形状必须钉住：打错路由的后端
// 会回 404，而界面那时已经把浮条藏了——用户以为停了，其实还在扣钱。

describe('cancelPdfSplitJob：彻底停止', () => {
  it('按任务主键取消（POST jobs/{id}/cancel）', async () => {
    splittingClient().post.mockReturnValue(respond({ job_id: 'job-9', status: 'cancelled' }))
    await expect(cancelPdfSplitJob('job-9')).resolves.toEqual({ job_id: 'job-9', status: 'cancelled' })
    expect(splittingClient().post).toHaveBeenCalledWith('jobs/job-9/cancel')
  })

  it('主键做 URL 编码：主键里出现特殊字符时也不能拼出一条错路径', async () => {
    splittingClient().post.mockReturnValue(respond({ job_id: 'a b', status: 'cancelled' }))
    await cancelPdfSplitJob('a b')
    expect(splittingClient().post).toHaveBeenCalledWith('jobs/a%20b/cancel')
  })

  it('失败直接抛：调用方必须能把「没停成」说出来（静默吞掉 = 谎报已停）', async () => {
    splittingClient().post.mockReturnValue(fail(new Error('500 Internal Server Error')))
    await expect(cancelPdfSplitJob('job-9')).rejects.toThrow('500')
  })
})

// ── 下载直链带人工转正角度 ────────────────────────────────────
//
// 旋转只记在草稿里，下载时靠 query 带出去；拼错分隔符（第二个 `?`）后端只会
// 收到一个叫 `?ids` 的垃圾参数，而浏览器导航的 4xx 进不了 JS——律师看到的是
// 「下载了但方向不对」，最难查的一类。

describe('下载直链：rotations', () => {
  it('单段 URL：无 query 时用 ?，有旋转才拼', () => {
    expect(segmentPdfUrl('job-1', 12)).toBe('/api/v1/pdf-splitting/jobs/job-1/segments/12/pdf')
    expect(segmentPdfUrl('job-1', 12, '3:90')).toBe(
      '/api/v1/pdf-splitting/jobs/job-1/segments/12/pdf?rotations=3%3A90',
    )
  })

  it('整包 URL：已有 ids 时用 & 续接（不能出现第二个 ?）', () => {
    const url = jobDownloadUrl('job-1', [12, 15], '3:90,4:90')
    expect(url).toBe('/api/v1/pdf-splitting/jobs/job-1/download?ids=12,15&rotations=3%3A90%2C4%3A90')
    expect(url.split('?')).toHaveLength(2)
  })

  it('空旋转不加参数：URL 与改动前逐字相同（日志/快照比对才有意义）', () => {
    expect(segmentPdfUrl('job-1', 12, '')).toBe(segmentPdfUrl('job-1', 12))
    expect(jobDownloadUrl('job-1', [3], '  ')).toBe(jobDownloadUrl('job-1', [3]))
  })
})

// ── 草稿导出：请求形状 ──────────────────────────────────────
//
// 服务端按**文件名**认领素材（`part_<partIndex>.<ext>`）。拼错这个名字的后果
// 不是报错，而是「导出包里少一份材料」——所以这里把 FormData 的字段逐个钉住。

describe('exportDraftZip', () => {
  function formEntries(body: FormData): Array<[string, string]> {
    return Array.from(body.entries()).map(([k, v]) => [k, typeof v === 'string' ? v : (v as File).name])
  }

  it('素材按 part_<序号>.<扩展名> 命名，spec 是 JSON 字符串', async () => {
    const post = vi.fn(async (_path: string, _opts: { body: FormData }) => respondWith(0))
    apiClientOf('/api/v1/pdf-splitting').post = post as never
    const { exportDraftZip } = await import('./pdf-split')
    await exportDraftZip({
      files: [
        { partIndex: 0, filename: '卷宗.pdf', blob: new Blob([new Uint8Array([1])], { type: 'application/pdf' }) },
        { partIndex: 7, filename: '现场照片.png', blob: new Blob([new Uint8Array([2])], { type: 'image/png' }) },
      ],
      segments: [{ name: '起诉状', part_index: 0, page_start: 1, page_end: 4 }],
      name: '某某案-起诉材料',
    })

    const [path, callOpts] = post.mock.calls[0]!
    // 客户端自带 /api/v1/pdf-splitting 前缀，这里只断言相对路径与编码后的包名
    expect(path).toBe('export-draft?name=%E6%9F%90%E6%9F%90%E6%A1%88-%E8%B5%B7%E8%AF%89%E6%9D%90%E6%96%99')
    const entries = formEntries(callOpts.body)
    expect(entries).toContainEqual(['files', 'part_0.pdf'])
    expect(entries).toContainEqual(['files', 'part_7.png'])
    // FormData.get 返回 string | File；这里是 spec 字段（字符串），显式断言类型
    const specField = callOpts.body.get('spec')
    expect(typeof specField).toBe('string')
    expect(JSON.parse(specField as string)).toEqual({
      segments: [{ name: '起诉状', part_index: 0, page_start: 1, page_end: 4 }],
    })
  })

  it('没有包名时不带 name 查询（URL 与默认一致）', async () => {
    const post = vi.fn(async (_path: string, _opts: { body: FormData }) => respondWith(2))
    apiClientOf('/api/v1/pdf-splitting').post = post as never
    const { exportDraftZip } = await import('./pdf-split')
    const result = await exportDraftZip({
      files: [{ partIndex: 0, filename: 'a.pdf', blob: new Blob([new Uint8Array([1])]) }],
      segments: [{ name: 'x', part_index: 0, page_start: 1, page_end: 1 }],
    })
    expect(post.mock.calls[0]![0]).toBe('export-draft')
    // 服务端跳过的段数从响应头回给调用方提示，不能静默少几份
    expect(result.skipped).toBe(2)
  })
})

/** 按 prefix 取客户端桩（导出用例要给 post 挂行为） */
function apiClientOf(prefix: string) {
  const hit = clients.find((c) => c.prefix === prefix)
  if (!hit) throw new Error(`客户端 ${prefix} 未创建`)
  return hit
}

/** 带 headers 的响应桩（exportDraftZip 要读 X-Export-Skipped） */
function respondWith(skipped = 0) {
  // ky 的 ResponsePromise：await 出来的是 Response 本身（带 headers 与 blob()）
  return Promise.resolve({
    blob: () => Promise.resolve(new Blob([new Uint8Array([9])], { type: 'application/zip' })),
    headers: { get: (name: string) => (name.toLowerCase() === 'x-export-skipped' ? String(skipped) : null) },
  })
}

/**
 * 提交任务时的两项**任务级选择**。
 *
 * 它们不是运维开关：分段策略决定分段 LLM 调用几遍，分歧裁定只在双引擎分歧上有事可做。
 * 契约只有两条要点——布尔值必须转成 `"1"/"0"`（后端按表单字符串解析），
 * 而**不传**与传 `false` 是两件事：前者让后端用自己的默认（开），后者是用户明确关掉。
 */
describe('createPdfSplitJob：分段策略与分歧裁定', () => {
  it('judge 传 false 时发 "0"（用户明确关掉，不能被后端默认覆盖）', async () => {
    splittingClient().post.mockReturnValue(respond({ job_id: 'j1', status: 'pending' }))
    await createPdfSplitJob(new File([new Uint8Array([1])], 'a.pdf'), {
      dualEngines: 'mineru,paddleocr_vl',
      segmentStrategy: 'wholebook_cross',
      ocrJudgeEnabled: false,
    })
    const body = splittingClient().post.mock.calls[0]![1].body as FormData
    expect(body.get('ocr_judge_enabled')).toBe('0')
    expect(body.get('segment_strategy')).toBe('wholebook_cross')
  })

  it('judge 传 true 时发 "1"；两项都不传时干脆不发（交由后端默认）', async () => {
    splittingClient().post.mockReturnValue(respond({ job_id: 'j2', status: 'pending' }))
    await createPdfSplitJob(new File([new Uint8Array([1])], 'b.pdf'), { ocrJudgeEnabled: true })
    const withJudge = splittingClient().post.mock.calls[0]![1].body as FormData
    expect(withJudge.get('ocr_judge_enabled')).toBe('1')
    expect(withJudge.get('segment_strategy')).toBeNull()

    splittingClient().post.mockReturnValue(respond({ job_id: 'j3', status: 'pending' }))
    await createPdfSplitJob(new File([new Uint8Array([1])], 'c.pdf'))
    const bare = splittingClient().post.mock.calls[1]![1].body as FormData
    expect(bare.get('ocr_judge_enabled')).toBeNull()
    expect(bare.get('segment_strategy')).toBeNull()
  })
})
