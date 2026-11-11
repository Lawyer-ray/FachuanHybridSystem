// @vitest-environment jsdom
/**
 * 整包 PDF 分段面板单测（jsdom）。
 *
 * 这是场景 2 的真正起点：一叠扫描件 → 分段 → 人工复核 → 归案。
 * 五步状态机（idle → uploading → splitting → review → confirming → done / failed）
 * 的每个转折都对应律师在屏幕上看到的一句不同的话，所以逐条钉住：
 *
 * - 模板跟案件阶段走：二审/重审/再审/提审 → appeal_defense_v1，否则 filing_materials_v1
 *   （模板选错 = 模型按错的材料身份预设，整包判成 unrecognized）
 * - 轮询到 review_required / completed → 进复核；failed / cancelled → 失败并带原因
 * - 轮询超过上限 → 失败并提示「任务可能仍在后台运行」
 * - 复核页显示需复核/未识别计数；「重来」清空回 idle
 * - 确认归案：segment_label 作为 type_name；side 由 guessSide 给出且**不为空**
 *   （category=party 时 side 空会被后端判「当事人方向不合法」，整个归案失败）
 * - 归案完成 → 「已归案 N 份」；任一步抛错 → 失败态带后端原话
 *
 * mock 只打 ../api；轮询间隔用「立刻触发」的 setTimeout 桩。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    createSplitJob: vi.fn(),
    getSplitJob: vi.fn(),
    confirmSplitJob: vi.fn(),
    downloadSplitZip: vi.fn(),
    uploadCaseMaterials: vi.fn(),
    bindMaterials: vi.fn(),
  }
})

import {
  bindMaterials,
  confirmSplitJob,
  createSplitJob,
  downloadSplitZip,
  getSplitJob,
  uploadCaseMaterials,
  type PdfSplitJob,
  type PdfSplitSegment,
} from '../api'
import { BundleSplitPanel } from './BundleSplitPanel'

const createJobMock = vi.mocked(createSplitJob)
const getJobMock = vi.mocked(getSplitJob)
const confirmMock = vi.mocked(confirmSplitJob)
const downloadMock = vi.mocked(downloadSplitZip)
const uploadMock = vi.mocked(uploadCaseMaterials)
const bindMock = vi.mocked(bindMaterials)

/**
 * 推进轮询。
 *
 * 轮询间隔是 POLL_MS = 2500ms，真等要十几分钟。这里用 vitest 的假定时器
 * 一次推进 >1 拍（2600ms），并 await advanceTimersByTimeAsync 让 promise 链跑完。
 * 每步都包在 act 里，避免 React 状态更新落在 act 之外。
 */
async function tick(ms = 2600) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

/** 反复推进直到条件成立（默认最多 20 拍） */
async function tickUntil(cond: () => boolean, maxTicks = 20, ms = 2600) {
  for (let i = 0; i < maxTicks; i++) {
    if (cond()) return
    await tick(ms)
  }
}

/** 打开文件选择框并塞一个 pdf。这里需要真的触发 start()。 */
function pickPdf(name = '整包.pdf') {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['%PDF'], name, { type: 'application/pdf' })] } })
}

function job(over: Partial<PdfSplitJob>): PdfSplitJob {
  return {
    job_id: 'j1',
    status: 'running',
    total_pages: 30,
    processed_pages: 0,
    segments: [],
    error_message: '',
    ...over,
  } as PdfSplitJob
}

/**
 * 拼一个只含 store 条目的最小 zip。
 *
 * 「归案成功」这条路径必须过 unzipToFiles：拿一个非 zip 的 blob 会在那一步
 * 就抛「分段结果为空」。store（method 0）不需要压缩，字节布局最简单。
 */
function makeZip(entries: Array<{ name: string; body: string }>): Blob {
  const enc = new TextEncoder()
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0

  for (const e of entries) {
    const nameBytes = enc.encode(e.name)
    const payload = enc.encode(e.body)

    const local = new Uint8Array(30 + nameBytes.length + payload.length)
    const lv = new DataView(local.buffer)
    lv.setUint32(0, 0x04034b50, true)
    lv.setUint16(8, 0, true) // method 0 = store
    lv.setUint32(18, payload.length, true)
    lv.setUint32(22, payload.length, true)
    lv.setUint16(26, nameBytes.length, true)
    local.set(nameBytes, 30)
    local.set(payload, 30 + nameBytes.length)
    locals.push(local)

    const central = new Uint8Array(46 + nameBytes.length)
    const cv = new DataView(central.buffer)
    cv.setUint32(0, 0x02014b50, true)
    cv.setUint16(10, 0, true)
    cv.setUint32(20, payload.length, true)
    cv.setUint32(24, payload.length, true)
    cv.setUint16(28, nameBytes.length, true)
    cv.setUint32(42, offset, true)
    central.set(nameBytes, 46)
    centrals.push(central)

    offset += local.length
  }

  const centralSize = centrals.reduce((n, c) => n + c.length, 0)
  const eocd = new Uint8Array(22)
  const ev = new DataView(eocd.buffer)
  ev.setUint32(0, 0x06054b50, true)
  ev.setUint16(8, entries.length, true)
  ev.setUint16(10, entries.length, true)
  ev.setUint32(12, centralSize, true)
  ev.setUint32(16, offset, true)

  const out = new Uint8Array(offset + centralSize + eocd.length)
  let p = 0
  for (const l of locals) {
    out.set(l, p)
    p += l.length
  }
  for (const c of centrals) {
    out.set(c, p)
    p += c.length
  }
  out.set(eocd, p)
  return new Blob([out as unknown as BlobPart])
}

function seg(over: Partial<PdfSplitSegment> & { id: number; filename: string }): PdfSplitSegment {
  return {
    order: over.id,
    page_start: 1,
    page_end: 2,
    segment_type: 'other',
    segment_label: '民事起诉状',
    confidence: 0.95,
    review_flag: 'ok',
    source_method: 'content',
    ...over,
  } as PdfSplitSegment
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  createJobMock.mockResolvedValue({ job_id: 'j1', status: 'queued' })
  // ⚠️ 默认带上一个分段：复核区有 `segs.length` 守卫，空数组会让整块不渲染，
  // 看着像「什么都没发生」—— 这不是组件的问题，是 fixture 的问题。
  getJobMock.mockResolvedValue(
    job({ status: 'review_required', processed_pages: 30, segments: [seg({ id: 1, filename: '01_民事起诉状.pdf' })] }),
  )
  confirmMock.mockResolvedValue({ job_id: 'j1', status: 'exporting' })
  downloadMock.mockResolvedValue(new Blob(['not-a-zip']))
  uploadMock.mockResolvedValue({ log_id: 1, attachment_ids: [11, 12] })
  bindMock.mockResolvedValue({ saved_count: 2 })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BundleSplitPanel · idle 态与模板选择', () => {
  it('idle 展示上传区、口径、历史记录、能力墙与规则', () => {
    render(<BundleSplitPanel caseId={406} />)

    expect(screen.getByText('上传一审起诉整包 PDF')).toBeTruthy()
    expect(screen.getByRole('button', { name: /选择整包 PDF/ })).toBeTruthy()
    expect(screen.getByText('本次拆分口径')).toBeTruthy()
    expect(screen.getByText('拆分记录')).toBeTruthy()
    expect(screen.getByText('上一次拆分明细')).toBeTruthy()
    expect(screen.getByText('识别能力')).toBeTruthy()
    expect(screen.getByText('拆分规则')).toBeTruthy()
    expect(screen.getByText('常见问题')).toBeTruthy()
    // idle 不该出现复核表或失败块
    expect(screen.queryByRole('button', { name: /确认并归案/ })).toBeNull()
    expect(screen.queryByText('处理失败')).toBeNull()
  })

  it('一审阶段用 filing_materials_v1；文案与统计格都是「一审起诉」', () => {
    render(<BundleSplitPanel caseId={406} stage="first_trial" />)
    expect(screen.getByText('filing_materials_v1')).toBeTruthy()
    expect(screen.getByText('一审起诉材料')).toBeTruthy()
    expect(screen.getAllByText('一审起诉').length).toBeGreaterThan(0)
  })

  it.each([
    ['second_trial', '中文/枚举的 second_trial'],
    ['retrial_second', 'retrial_second'],
    ['rehearing_second', 'rehearing_second'],
    ['review', 'review（提审）'],
    ['二审', '历史中文存量「二审」'],
    ['重审二审', '历史中文存量「重审二审」'],
    ['再审二审', '历史中文存量「再审二审」'],
    ['提审', '历史中文存量「提审」'],
  ])('二审类阶段 %s 一律切到 appeal_defense_v1（%s）', (stage) => {
    render(<BundleSplitPanel caseId={406} stage={stage} />)
    expect(screen.getByText('appeal_defense_v1')).toBeTruthy()
    expect(screen.getByText('二审答辩材料')).toBeTruthy()
    expect(screen.getByText('上传二审答辩整包 PDF')).toBeTruthy()
    // 反过来，一审模板号不该出现
    expect(screen.queryByText('filing_materials_v1')).toBeNull()
  })

  it('stage 为空时按一审模板处理（不能因为没阶段就丢掉模板号）', () => {
    render(<BundleSplitPanel caseId={406} stage={null} />)
    expect(screen.getByText('filing_materials_v1')).toBeTruthy()
  })
})

describe('BundleSplitPanel · 上传与轮询', () => {
  it('选包后立刻提交任务，模板跟着阶段一起传下去', async () => {
    getJobMock.mockResolvedValue(
      job({ status: 'review_required', segments: [seg({ id: 1, filename: '01_上诉状.pdf' })] }),
    )
    render(<BundleSplitPanel caseId={406} stage="second_trial" />)

    pickPdf('二审整包.pdf')
    await tickUntil(() => getJobMock.mock.calls.length > 0)

    expect(createJobMock).toHaveBeenCalledTimes(1)
    expect(createJobMock.mock.calls[0]![0]).toBeInstanceOf(File)
    expect(createJobMock.mock.calls[0]![1]).toBe('appeal_defense_v1')
  })

  it('轮询中显示「识别中 N/M 页」，exporting 时换成导出文案', async () => {
    getJobMock
      .mockResolvedValueOnce(job({ status: 'running', processed_pages: 12, total_pages: 30 }))
      .mockResolvedValueOnce(job({ status: 'exporting', processed_pages: 30, total_pages: 30 }))
      .mockResolvedValue(
        job({
          status: 'review_required',
          processed_pages: 30,
          total_pages: 30,
          segments: [seg({ id: 1, filename: 'a.pdf' })],
        }),
      )

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()

    await tickUntil(() => screen.queryByText('识别中 12/30 页') !== null)
    expect(screen.getByText('识别中 12/30 页')).toBeTruthy()
    expect(screen.getByText('12/30 页')).toBeTruthy() // 进度条右侧的计数
    await tickUntil(() => screen.queryByText('正在导出分段文件…') !== null)
    expect(screen.getByText('正在导出分段文件…')).toBeTruthy()
  })

  it('后端没给总页数时用「?」占位（不要显示 0）', async () => {
    let firstPoll = true
    getJobMock.mockImplementation(async () => {
      if (firstPoll) {
        firstPoll = false
        return job({ status: 'running', processed_pages: 3, total_pages: null as never })
      }
      return job({ status: 'review_required', segments: [seg({ id: 1, filename: 'a.pdf' })] })
    })

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByText('识别中 3/? 页') !== null)
    expect(screen.getByText('识别中 3/? 页')).toBeTruthy()
  })

  it('review_required 进入复核页：显示份数与复核表', async () => {
    const segments = [seg({ id: 1, filename: 'a.pdf' }), seg({ id: 2, filename: 'b.pdf' })]
    getJobMock.mockResolvedValue(job({ status: 'review_required', segments }))

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()

    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()
    expect(screen.getByText('共识别')).toBeTruthy()
    expect(screen.getByText('2', { selector: 'span.tabular-nums' })).toBeTruthy()
    expect(screen.getByText('确认后会导出 2 个 PDF 并自动挂到本案')).toBeTruthy()
    expect(screen.getByText('a.pdf')).toBeTruthy()
    expect(screen.getByText('b.pdf')).toBeTruthy()
  })

  it('completed 也直接进复核（后端可能一次跑完），不必等 review_required', async () => {
    getJobMock.mockResolvedValue(job({ status: 'completed', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()
  })

  it('复核页标出需复核 / 未识别份数（这两类才是要人盯的）', async () => {
    getJobMock.mockResolvedValue(
      job({
        status: 'review_required',
        segments: [
          seg({ id: 1, filename: 'a.pdf', review_flag: 'ok' }),
          seg({ id: 2, filename: 'b.pdf', review_flag: 'low_confidence', confidence: 0.72 }),
          seg({ id: 3, filename: 'c.pdf', review_flag: 'unrecognized', confidence: 0.4 }),
        ],
      }),
    )
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()

    await tickUntil(() => screen.queryByText('1 份需复核') !== null)
    expect(screen.getByText('1 份未识别')).toBeTruthy()
  })

  it('failed 显示后端 error_message；cancelled 显示「分段已取消」', async () => {
    getJobMock.mockResolvedValueOnce(job({ status: 'failed', error_message: 'OCR 代理超时' }))
    const first = render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByText('处理失败') !== null)
    expect(screen.getByText('处理失败')).toBeTruthy()
    expect(screen.getByText('OCR 代理超时')).toBeTruthy()
    first.unmount()

    getJobMock.mockReset()
    getJobMock.mockResolvedValue(job({ status: 'cancelled' }))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByText('分段已取消') !== null)
    expect(screen.getByText('分段已取消')).toBeTruthy()
  })

  it('提交任务失败（连 job 都没建出来）→ 失败态带原话', async () => {
    createJobMock.mockRejectedValue(new Error('上传超时'))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()

    await tickUntil(() => screen.queryByText('上传超时') !== null)
    expect(screen.getByText('上传超时')).toBeTruthy()
    expect(screen.getByText('处理失败')).toBeTruthy()
  })

  it('「重试」把失败态清回 idle，可以从头再传一包', async () => {
    createJobMock.mockRejectedValue(new Error('上传超时'))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByText('处理失败') !== null)
    expect(screen.getByText('处理失败')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(screen.getByText('上传一审起诉整包 PDF')).toBeTruthy()
    expect(screen.queryByText('处理失败')).toBeNull()
  })

  it('「重来」在复核页把状态清回 idle', async () => {
    getJobMock.mockResolvedValue(job({ status: 'review_required', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /重来/ }) !== null)
    expect(screen.getByRole('button', { name: /重来/ })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /重来/ }))
    expect(screen.getByText('上传一审起诉整包 PDF')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /确认并归案/ })).toBeNull()
  })
})

describe('BundleSplitPanel · 确认归案', () => {
  it('确认分段时 segment_type 原样带进 payload，side 与文件名对上 attachment_id', async () => {
    const segments = [
      seg({ id: 1, filename: '01_民事起诉状.pdf', segment_type: '民事起诉状', segment_label: '民事起诉状', order: 1 }),
      seg({ id: 2, filename: '02_被告身份证.pdf', segment_type: '被告身份证', segment_label: '被告身份证', order: 2 }),
    ]
    getJobMock.mockResolvedValue(job({ status: 'review_required', segments }))

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /确认并归案/ }))

    await tickUntil(() => confirmMock.mock.calls.length > 0)
    expect(confirmMock).toHaveBeenCalled()
    const [, payload] = confirmMock.mock.calls[0]!
    expect(payload).toHaveLength(2)
    // 提交项只有一个类型字段 segment_type（没有 type_name）：原样把它带下去，
    // 不被空值替换成 unrecognized。
    expect(payload[0]!.segment_type).toBe('民事起诉状')
    expect(payload[0]!.filename).toBe('01_民事起诉状.pdf')
    // 页码区间原样带下去
    expect(payload[0]!.page_start).toBe(1)
    expect(payload[0]!.page_end).toBe(2)
  })

  it('归案成功后显示「已归案 N 份」', async () => {
    const segments = [
      seg({ id: 1, filename: '01_民事起诉状.pdf' }),
      seg({ id: 2, filename: '02_借款合同.pdf' }),
    ]
    getJobMock.mockResolvedValueOnce(job({ status: 'review_required', segments }))
    // 确认之后的导出轮询：一次就 completed
    getJobMock.mockResolvedValue(job({ status: 'completed', segments }))

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()

    // 下载回真 zip（两个条目），否则会在 unzip 那步抛「分段结果为空」
    downloadMock.mockResolvedValue(
      makeZip([
        { name: '01_民事起诉状.pdf', body: '%PDF-1' },
        { name: '02_借款合同.pdf', body: '%PDF-2' },
      ]),
    )
    fireEvent.click(screen.getByRole('button', { name: /确认并归案/ }))

    // bindMaterials 回 saved_count=2（见 beforeEach），界面照后端数报
    await tickUntil(() => screen.queryByText('已归案 2 份材料') !== null)
    expect(screen.getByText('已归案 2 份材料')).toBeTruthy()
    expect(screen.getByText(/切到「起诉条件」看材料齐备度/)).toBeTruthy()

    // 归案项：category 固定 party，side 必须是 our / opponent 且**不为空**
    // （后端校验 side not in {OUR, OPPONENT} 直接报「当事人方向不合法」）
    expect(bindMock).toHaveBeenCalledTimes(1)
    const [boundCaseId, items] = bindMock.mock.calls[0]!
    expect(boundCaseId).toBe(406)
    expect(items).toHaveLength(2)
    for (const it of items) {
      expect(it.category).toBe('party')
      expect(['our', 'opponent']).toContain(it.side)
      // 类型名取引擎识别的 segment_label，不能自己另起名字（材料齐备度按类型名关键词匹配）
      expect(it.type_name).toBe('民事起诉状')
    }
    expect(items.map((i) => i.attachment_id)).toEqual([11, 12])

    // 两个文件都上传了
    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock.mock.calls[0]![0]).toBe(406)
    expect(uploadMock.mock.calls[0]![1].map((f) => f.name)).toEqual([
      '01_民事起诉状.pdf',
      '02_借款合同.pdf',
    ])
  })

  it('导出阶段失败 → 失败态带后端原话', async () => {
    getJobMock.mockResolvedValueOnce(job({ status: 'review_required', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()

    // 确认之后轮询：直接判 failed
    getJobMock.mockResolvedValue(job({ status: 'failed', error_message: '导出磁盘满' }))
    fireEvent.click(screen.getByRole('button', { name: /确认并归案/ }))

    await tickUntil(() => screen.queryByText('导出磁盘满') !== null)
    expect(screen.getByText('导出磁盘满')).toBeTruthy()
  })

  it('下载结果为空（分段结果为空）→ 失败态', async () => {
    getJobMock.mockResolvedValueOnce(job({ status: 'review_required', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    expect(screen.getByRole('button', { name: /确认并归案/ })).toBeTruthy()

    getJobMock.mockResolvedValue(job({ status: 'completed', segments: [] }))
    // 不是 zip 的字节 → unzipToFiles 返回空数组
    downloadMock.mockResolvedValue(new Blob([new Uint8Array(64).fill(0x41)]))
    fireEvent.click(screen.getByRole('button', { name: /确认并归案/ }))

    await tickUntil(() => screen.queryByText('分段结果为空') !== null)
    expect(screen.getByText('分段结果为空')).toBeTruthy()
  })

  it('「再传一包」从完成态回到 idle', async () => {
    getJobMock.mockResolvedValueOnce(job({ status: 'review_required', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    getJobMock.mockResolvedValue(job({ status: 'completed', segments: [seg({ id: 1, filename: 'a.pdf' })] }))
    downloadMock.mockResolvedValue(makeZip([{ name: 'a.pdf', body: '%PDF-1' }]))

    render(<BundleSplitPanel caseId={406} />)
    pickPdf()
    await tickUntil(() => screen.queryByRole('button', { name: /确认并归案/ }) !== null)
    fireEvent.click(screen.getByRole('button', { name: /确认并归案/ }))

    await tickUntil(() => screen.queryByRole('button', { name: '再传一包' }) !== null)
    expect(screen.getByRole('button', { name: '再传一包' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '再传一包' }))
    expect(screen.getByText('上传一审起诉整包 PDF')).toBeTruthy()
  })
})
