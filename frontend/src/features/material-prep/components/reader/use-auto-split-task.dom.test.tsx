// @vitest-environment jsdom
/**
 * 自动分段任务会话态 / 接管测试（jsdom）。
 *
 * 守的是一条真实事故：任务以前只活在发起页面的内存里，刷新 / 换设备 / 由同事发起
 * 时前端一无所知（「幽灵任务」），律师要么看不到进度、要么再点一次并行烧第二份钱。
 * 所以这里覆盖：
 * - 打开阅读器时命中 inflight 任务 → 自动接管轮询并上报进度（不需要点按钮）
 * - 命中后轮询到终态 → 会话态清空（面板消失）
 * - 没有命中 / 页数未知 → 不发多余的探测请求，也不进入轮询
 * - 完结任务不清空别的任务
 * - 「不再显示」只收起界面、不动任务
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  findInflightPdfSplitJob: vi.fn(),
  getPdfSplitJob: vi.fn(),
  cancelPdfSplitJob: vi.fn(),
}))
vi.mock('../../api', () => apiMock)
// 包号从阅读器 store 读（`useReader((s) => s.openId)`）：这里给个可改的替身，
// 免得把 pdf.js 一整套真实依赖拉进 jsdom。
const readerMock = vi.hoisted(() => ({ openId: 617 }))
vi.mock('../../store', () => ({
  useReader: (selector: (s: { openId: number }) => unknown) => selector({ openId: readerMock.openId }),
}))

import { pollJob } from './auto-split-helpers'
import type { BundleMat } from '../../types'
import {
  beginOwnedAutoSplit,
  clearAutoSplitTask,
  readAutoSplitTask,
  reportAutoSplitProgress,
  stopCurrentAutoSplitTask,
  useInflightAutoSplit,
  type JobProgressSnapshot,
} from './use-auto-split-task'

function pdfMat(n: string, pages = 164, extra: Partial<BundleMat> = {}): BundleMat {
  return { partIndex: 0, n, k: 'pdf', pages, customName: '', ...extra }
}

function snap(over: Partial<JobProgressSnapshot> = {}): JobProgressSnapshot {
  return {
    jobId: 'job-1',
    status: 'processing',
    stage: 'extract',
    progressPct: 40,
    processedPages: 60,
    totalPages: 164,
    elapsedSeconds: 90,
    staleSeconds: 2,
    errorMessage: '',
    dualEngines: '',
    sourceName: '',
    ...over,
  }
}

/** 测试用的材料包主键：会话态按包归属，所有调用都要带上它 */
const PACK = 617
/** 另一个材料包（用来验证「A 包的进度条不许出现在 B 包上」） */
const OTHER_PACK = 601

beforeEach(() => {
  vi.clearAllMocks()
  clearAutoSplitTask()
  readerMock.openId = PACK
  apiMock.findInflightPdfSplitJob.mockResolvedValue(null)
  apiMock.cancelPdfSplitJob.mockResolvedValue({ job_id: 'job-1', status: 'cancelled' })
})

afterEach(() => {
  clearAutoSplitTask()
})

/**
 * 让轮询停在下一份快照上，用例才能断言「对话态此刻长什么样」。
 *
 * 不能直接 mock 一个立刻到达终态的响应：接管收尾会把会话态清空，而清空发生在
 * 微任务里——同一次同步断言只能读到「已清空」，读不到「跑起来过」。所以要按住
 * 第一份 processing 快照，等断言完再放行。
 */
function holdNextPoll() {
  let release: (job: Record<string, unknown>) => void = () => {}
  apiMock.getPdfSplitJob.mockImplementation(
    () => new Promise((resolve) => {
      release = resolve
    }),
  )
  return (job: Record<string, unknown>) => release(job)
}

describe('useInflightAutoSplit：打开阅读器自动接管', () => {
  it('命中进行中的任务时自动接管并上报快照（无需点按钮）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-9',
      status: 'processing',
      progress: 55,
      total_pages: 164,
      processed_pages: 90,
      stage: 'cross_check',
      dual_engines: 'mineru,paddleocr_vl',
      elapsed_seconds: 400,
      stale_seconds: 3,
    })
    const release = holdNextPoll()

    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('证据材料.pdf')], true))

    // 探测请求必须带文件名 + 页数（后端靠这两个匹配同一份卷宗）
    await waitFor(() => {
      expect(apiMock.findInflightPdfSplitJob).toHaveBeenCalledWith({
      packMessageId: PACK,
      sourceName: '证据材料.pdf',
      totalPages: 164,
    })
    })
    // 命中后立刻接管轮询
    await waitFor(() => expect(apiMock.getPdfSplitJob).toHaveBeenCalledWith('job-9'))

    release({
      job_id: 'job-9',
      status: 'processing',
      progress: 100,
      total_pages: 164,
      processed_pages: 164,
      stage: 'cross_check',
      elapsed_seconds: 460,
      stale_seconds: 4,
    })
    await waitFor(() => expect(result.current.task.snapshot?.stage).toBe('cross_check'))
    // 接管来的任务标成「非本人发起」：终态不允许回写草稿
    expect(result.current.task.owned).toBe(false)
    expect(result.current.task.jobId).toBe('job-9')
    // 快照带源文件名，面板据此显示「这是别人发起的那份」
    expect(result.current.task.snapshot?.sourceName).toBe('证据材料.pdf')
  })

  it('首份快照直接来自探测响应（面板不必再请求一次）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-2',
      status: 'processing',
      progress: 100,
      total_pages: 164,
      processed_pages: 164,
      stage: 'segment',
      elapsed_seconds: 800,
      stale_seconds: 4,
    })
    holdNextPoll()
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('卷宗.pdf')], true))

    await waitFor(() => expect(result.current.task.snapshot?.jobId).toBe('job-2'))
    expect(result.current.task.snapshot?.stage).toBe('segment')
    expect(result.current.task.snapshot?.elapsedSeconds).toBe(800)
    expect(result.current.task.snapshot?.sourceName).toBe('卷宗.pdf')
  })

  it('轮询到终态后会话态清空（面板消失）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-3',
      status: 'processing',
      progress: 100,
      total_pages: 164,
      processed_pages: 164,
      stage: 'segment',
    })
    const release = holdNextPoll()
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('卷宗.pdf')], true))
    await waitFor(() => expect(result.current.task.jobId).toBe('job-3'))

    release({ status: 'completed', segments: [], summary: {} })
    await waitFor(() => expect(result.current.task.jobId).toBeNull())
  })

  it('探测失败（网络异常）不阻断阅读器，也不进入接管态', async () => {
    apiMock.findInflightPdfSplitJob.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('a.pdf')], true))
    await waitFor(() => expect(apiMock.findInflightPdfSplitJob).toHaveBeenCalled())
    expect(result.current.task.jobId).toBeNull()
  })

  it('没有进行中的任务时不进入接管态', async () => {
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('a.pdf')], true))
    await waitFor(() => expect(apiMock.findInflightPdfSplitJob).toHaveBeenCalled())
    expect(result.current.task.jobId).toBeNull()
    expect(result.current.task.snapshot).toBeNull()
    expect(apiMock.getPdfSplitJob).not.toHaveBeenCalled()
  })

  it('页数未知的 PDF 不探测（猜出来的页数只会查出空集）', async () => {
    renderHook(() => useInflightAutoSplit([pdfMat('a.pdf', 1, { pagesUnknown: true })], true))
    await waitFor(() => expect(apiMock.findInflightPdfSplitJob).not.toHaveBeenCalled())
  })

  it('非 PDF 素材不探测', async () => {
    const photo: BundleMat = { partIndex: 0, n: 'b.jpg', k: 'photo', pages: 1 }
    renderHook(() => useInflightAutoSplit([photo], true))
    await waitFor(() => expect(apiMock.findInflightPdfSplitJob).not.toHaveBeenCalled())
  })

  it('草稿未就绪（enabled=false）时不探测', async () => {
    renderHook(() => useInflightAutoSplit([pdfMat('a.pdf')], false))
    await waitFor(() => expect(apiMock.findInflightPdfSplitJob).not.toHaveBeenCalled())
  })

  it('已有在手任务时不抢成接管（否则终态不回写草稿）', async () => {
    // 模拟「用户先点了按钮、组件随后才挂载」：探测必须让位给在手任务，
    // 否则这次轮询的 owned 会被改成 false，跑完不回写草稿、钱白花
    beginOwnedAutoSplit(PACK, snap({ jobId: 'mine' }))
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('a.pdf')], true))
    // 探测是异步的（等一个微任务），给足一拍再断言「没发出去」
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(apiMock.findInflightPdfSplitJob).not.toHaveBeenCalled()
    expect(result.current.task.jobId).toBe('mine')
    expect(result.current.task.owned).toBe(true)
  })
})

describe('useInflightAutoSplit：会话态生命周期', () => {
  it('「不再显示」只收起界面，任务仍在跑', () => {
    beginOwnedAutoSplit(PACK, snap())
    const { result } = renderHook(() => useInflightAutoSplit([], false))
    act(() => result.current.hide())
    expect(result.current.task.hidden).toBe(true)
    expect(result.current.task.jobId).toBe('job-1')
  })

  it('clearAutoSplitTask 清空会话态', () => {
    beginOwnedAutoSplit(PACK, snap())
    const { result } = renderHook(() => useInflightAutoSplit([], false))
    expect(result.current.task.jobId).toBe('job-1')
    act(() => clearAutoSplitTask())
    expect(result.current.task.jobId).toBeNull()
  })

  it('轮询回报的快照会更新到会话态（面板据此刷新进度）', () => {
    beginOwnedAutoSplit(PACK, snap())
    const { result } = renderHook(() => useInflightAutoSplit([], false))
    act(() => reportAutoSplitProgress(PACK, snap({ processedPages: 120, progressPct: 73 })))
    expect(result.current.task.snapshot?.processedPages).toBe(120)
  })
})

describe('useInflightAutoSplit：任务归属材料包（2026-11-26 报障）', () => {
  /**
   * 用户报障：打开 601 号材料包，底部浮条上显示着 617 号那份任务的
   * 「正在识别文字（0/37 页）」。两条路都会漏——会话态是模块级的，换包既不清空
   * 也不看包号；「已有在手任务就不探测」还把别的包的任务当成了在手任务。
   */
  it('别的包的任务不上界面：第一帧就不给，等本包的探测结果', async () => {
    // 律师刚从 617 切过来，那一份任务的会话态还在模块里
    beginOwnedAutoSplit(OTHER_PACK, snap({ jobId: 'other-pack-job' }))

    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('材料.pdf')], true))

    // 渲染期就按包号过滤过，不是等 effect 跑完才消失（否则会闪一帧别人的进度）
    expect(result.current.task.jobId).toBeNull()
    // 也不能被「已有在手任务」挡掉：必须为本包重新探测
    await waitFor(() =>
      expect(apiMock.findInflightPdfSplitJob).toHaveBeenCalledWith({
        packMessageId: PACK,
        sourceName: '材料.pdf',
        totalPages: 164,
      }),
    )
  })

  it('换包后上一个包的会话态被撤掉（不留没有主人的幽灵浮条）', async () => {
    beginOwnedAutoSplit(OTHER_PACK, snap({ jobId: 'other-pack-job' }))

    renderHook(() => useInflightAutoSplit([pdfMat('材料.pdf')], true))

    await waitFor(() => expect(readAutoSplitTask().packId).not.toBe(OTHER_PACK))
    expect(readAutoSplitTask().jobId).toBeNull()
  })

  it('别的包的进度回报一律丢弃（切包后迟到的快照不许跨包落地）', () => {
    beginOwnedAutoSplit(OTHER_PACK, snap({ jobId: 'other-pack-job', processedPages: 60 }))
    renderHook(() => useInflightAutoSplit([], false))

    act(() => reportAutoSplitProgress(PACK, snap({ processedPages: 999 })))

    expect(readAutoSplitTask().snapshot?.processedPages).toBe(60)
  })

  it('本包探测到的任务照常接管（包过滤不能把正常接管一起关掉）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-mine',
      status: 'processing',
      progress: 20,
      total_pages: 37,
      processed_pages: 7,
      stage: 'extract',
      stale_seconds: 2,
    })
    holdNextPoll()

    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('材料.pdf', 37)], true))

    await waitFor(() => expect(result.current.task.jobId).toBe('job-mine'))
    expect(result.current.task.packId).toBe(PACK)
  })
})

describe('useInflightAutoSplit：彻底停止（取消云端任务）', () => {
  it('「停止识别」打到后端取消接口，并把会话态清空（浮条随之消失）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-stop',
      status: 'processing',
      progress: 10,
      total_pages: 37,
      processed_pages: 3,
      stage: 'extract',
      stale_seconds: 2,
    })
    holdNextPoll()
    const { result } = renderHook(() => useInflightAutoSplit([pdfMat('材料.pdf', 37)], true))
    await waitFor(() => expect(result.current.task.jobId).toBe('job-stop'))

    await act(async () => {
      await stopCurrentAutoSplitTask()
    })

    expect(apiMock.cancelPdfSplitJob).toHaveBeenCalledWith('job-stop')
    expect(readAutoSplitTask().jobId).toBeNull()
  })

  it('取消失败时**不**清会话态：静默藏掉浮条等于谎称「停了」，而任务还在扣钱', async () => {
    apiMock.cancelPdfSplitJob.mockRejectedValue(new Error('503 Service Unavailable'))
    beginOwnedAutoSplit(PACK, snap({ jobId: 'job-x' }))

    const { result } = renderHook(() => useInflightAutoSplit([], false))
    await act(async () => {
      await stopCurrentAutoSplitTask()
    })

    // 浮条还在、还能再按一次
    expect(readAutoSplitTask().jobId).toBe('job-x')
    expect(result.current.task.jobId).toBe('job-x')
  })

  it('还没拿到任务号（提交那几十秒）也能停：停本地即可，不必等服务端', async () => {
    beginOwnedAutoSplit(PACK) // jobId 仍为 null

    renderHook(() => useInflightAutoSplit([], false))
    await act(async () => {
      await stopCurrentAutoSplitTask()
    })

    expect(apiMock.cancelPdfSplitJob).not.toHaveBeenCalled()
    expect(readAutoSplitTask().jobId).toBeNull()
  })
})

describe('pollJob：阶段化进度回调', () => {
  it('同时交出文字与结构化快照', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({
      job_id: 'job-3',
      status: 'processing',
      progress: 50,
      total_pages: 164,
      processed_pages: 82,
      stage: 'extract',
      elapsed_seconds: 120,
      stale_seconds: 3,
    })
    const lease = { isStale: () => true, sleep: () => Promise.resolve() }
    // lease 立刻过期：只跑一轮就退出，足够看回调
    await pollJob('job-3', lease, () => {}).catch(() => {})

    const seen: { text: string; snapshot: JobProgressSnapshot }[] = []
    const recording = { isStale: () => false, sleep: () => Promise.resolve() }
    apiMock.getPdfSplitJob.mockResolvedValue({ status: 'completed', segments: [], summary: {} })
    await pollJob('job-3', recording, (text, snapshot) => seen.push({ text, snapshot }))
    // 终态不再回调进度（status 是 completed 直接返回）
    expect(seen).toHaveLength(0)
  })

  it('取字阶段文字报页数，交叉比对阶段改说「比对中」', async () => {
    const seen: { text: string; snapshot: JobProgressSnapshot }[] = []
    apiMock.getPdfSplitJob
      .mockResolvedValueOnce({
        job_id: 'job-4',
        status: 'processing',
        progress: 50,
        total_pages: 164,
        processed_pages: 82,
        stage: 'extract',
      })
      .mockResolvedValueOnce({
        job_id: 'job-4',
        status: 'processing',
        progress: 100,
        total_pages: 164,
        processed_pages: 164,
        stage: 'cross_check',
      })
      .mockResolvedValueOnce({ status: 'completed', segments: [], summary: {} })
    const lease = { isStale: () => false, sleep: () => Promise.resolve() }
    await pollJob('job-4', lease, (text, snapshot) => seen.push({ text, snapshot }))

    expect(seen[0]?.text).toBe('正在识别 82/164 页（50%）')
    expect(seen[0]?.snapshot.stage).toBe('extract')
    expect(seen[1]?.text).toBe('双引擎交叉比对中…')
    expect(seen[1]?.snapshot.stage).toBe('cross_check')
  })

  it('tolerateStale：心跳停了只提示、不抛错（接管别人的任务时由用户决定）', async () => {
    apiMock.getPdfSplitJob
      .mockResolvedValueOnce({
        job_id: 'job-5',
        status: 'processing',
        progress: 60,
        total_pages: 164,
        processed_pages: 100,
        stage: 'extract',
        stale_seconds: 900,
      })
      .mockResolvedValueOnce({ status: 'completed', segments: [], summary: {} })
    const lease = { isStale: () => false, sleep: () => Promise.resolve() }

    const job = await pollJob('job-5', lease, () => {}, true)
    expect(job.status).toBe('completed')
  })

  it('自己发起的任务心跳停了仍然立刻失败并说明原因', async () => {
    apiMock.getPdfSplitJob.mockResolvedValue({
      job_id: 'job-6',
      status: 'processing',
      progress: 60,
      total_pages: 164,
      processed_pages: 100,
      stage: 'extract',
      stale_seconds: 900,
    })
    const lease = { isStale: () => false, sleep: () => Promise.resolve() }
    await expect(pollJob('job-6', lease)).rejects.toThrow(/已中断/)
  })
})

describe('useInflightAutoSplit：接管时的两个防御分支', () => {
  /**
   * 探测失败必须**就地吞掉**并继续看下一份材料。
   *
   * 为什么单独测这条：探测只是「看看有没有人在跑」的附加信息，一个网络抖动
   * 若变成未捕获拒绝，CI 会整批红，开发态还会弹一个与用户操作无关的错。
   * 而「吞掉」不等于「放弃」——第一份失败不该让第二份的在飞任务接管不到。
   */
  it('第一份材料探测抛错 → 继续看下一份，接管到第二份的任务', async () => {
    apiMock.findInflightPdfSplitJob.mockImplementation((args: { sourceName: string }) =>
      args.sourceName === '坏链接.pdf'
        ? Promise.reject(new Error('Network request failed'))
        : Promise.resolve({
            job_id: 'job-next',
            status: 'processing',
            progress: 10,
            total_pages: 164,
            processed_pages: 16,
            stage: 'extract',
            stale_seconds: 2,
          }),
    )
    holdNextPoll()

    const { result } = renderHook(() =>
      useInflightAutoSplit([pdfMat('坏链接.pdf'), pdfMat('卷宗.pdf')], true),
    )

    await waitFor(() => expect(result.current.task.jobId).toBe('job-next'))
    expect(apiMock.findInflightPdfSplitJob).toHaveBeenNthCalledWith(1, {
      packMessageId: PACK,
      sourceName: '坏链接.pdf',
      totalPages: 164,
    })
    expect(apiMock.findInflightPdfSplitJob).toHaveBeenNthCalledWith(2, {
      packMessageId: PACK,
      sourceName: '卷宗.pdf',
      totalPages: 164,
    })
    expect(result.current.task.snapshot?.sourceName).toBe('卷宗.pdf')
  })

  /**
   * 接管来的轮询回调要在 lease 失效后立刻弃写。
   *
   * 场景：律师在这份任务还在跑的时候切了材料包（或对战/归案跳走了），
   * 旧会话已经过期，此时后端刚好回了一份旧快照——若照样 setState，
   * 浮条会重新亮起来，显示一个已经不存在的任务，还挡着新页面。
   */
  it('lease 失效后迟到的快照不写进会话态（切走后浮条不该再亮）', async () => {
    apiMock.findInflightPdfSplitJob.mockResolvedValue({
      job_id: 'job-late',
      status: 'processing',
      progress: 40,
      total_pages: 164,
      processed_pages: 60,
      stage: 'extract',
      stale_seconds: 2,
    })
    const release = holdNextPoll()

    const hook = renderHook(() => useInflightAutoSplit([pdfMat('卷宗.pdf')], true))
    await waitFor(() => expect(hook.result.current.task.jobId).toBe('job-late'))

    // 卸载 = 轮询会话失效（usePollSession 的 unmounted 闸门）
    hook.unmount()
    release({
      job_id: 'job-late',
      status: 'processing',
      progress: 90,
      total_pages: 164,
      processed_pages: 148,
      stage: 'segment',
    })
    // 给迟到回调一拍执行机会
    await new Promise((resolve) => setTimeout(resolve, 20))

    // 模块级会话态没有被这次迟到回调改写（仍是接管时那份快照）：
    // 浮条读的就是它，写成 segment/148 页就等于在律师已经切走的页面上重新亮起
    const task = readAutoSplitTask()
    expect(task.jobId).toBe('job-late')
    expect(task.snapshot?.stage).toBe('extract')
    expect(task.snapshot?.processedPages).toBe(60)
  })
})
