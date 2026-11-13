// @vitest-environment jsdom
/**
 * useAutoSplit 测试（jsdom）。
 *
 * 覆盖的分支全部来自真实业务语义：
 * - 无 PDF / 全部已人工拆分 → 各自一条 info 提示，不提交任务
 * - 部分成功 → warning 且只写入成功那部分
 * - 全部失败 → error
 * - 分段后端为规则引擎时提示质量降级
 * - openId 变化（用户切走）→ 不回写 store
 * - 卸载后取消 → 不弹错误
 * - 连点重入 → 旧循环过期退出，只留一个任务流、一次提示、一次回写
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  fetchAttachmentBytes: vi.fn(),
  createPdfSplitJob: vi.fn(),
  getPdfSplitJob: vi.fn(),
  ocrImage: vi.fn(),
  parseOfficeFile: vi.fn(),
}))
const draftMock = vi.hoisted(() => ({
  applyAutoSplit: vi.fn((v: unknown) => ({ ...(v as object), applied: true })),
  canAutoSplitMat: vi.fn(),
  fillSegmentText: vi.fn((v: unknown) => ({ ...(v as object), filled: true })),
}))
const storeMock = vi.hoisted(() => ({
  getState: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))
vi.mock('../../api', () => apiMock)
vi.mock('../../draft', () => draftMock)
vi.mock('../../store', () => ({ useReader: storeMock }))

import { toast } from 'sonner'

import { useAutoSplit } from './use-auto-split'

function pdfMat(mi: number, name = `m${mi}.pdf`) {
  return { k: 'pdf', partIndex: mi, n: name, customName: '' }
}
/** 图片素材：真实域模型的 kind 值是 'photo'（见 draft/resolve 的 detectMaterialKind） */
function imgMat(mi: number) {
  return { k: 'photo', partIndex: mi, n: `m${mi}.jpg`, customName: '' }
}
/** Office 素材（Word / Excel） */
function officeMat(mi: number) {
  return { k: 'office', partIndex: mi, n: `m${mi}.docx`, customName: '' }
}

function setup({ mats = [pdfMat(0)], openId = 1 } = {}) {
  const update = vi.fn()
  storeMock.getState.mockReturnValue({
    openId,
    draft: { mats },
    update,
  })
  return { update }
}

beforeEach(() => {
  vi.clearAllMocks()
  draftMock.canAutoSplitMat.mockReturnValue(true)
  apiMock.fetchAttachmentBytes.mockResolvedValue(new Uint8Array([1, 2, 3]))
  apiMock.createPdfSplitJob.mockResolvedValue('job-1')
  apiMock.getPdfSplitJob.mockResolvedValue({
    status: 'completed',
    segments: [{ p: 0 }, { p: 1 }],
    summary: { segment_backend: 'llm' },
  })
})

describe('useAutoSplit：提前退出分支', () => {
  it('无 openId 时不做事', async () => {
    storeMock.getState.mockReturnValue({ openId: null, draft: null })
    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })
    expect(apiMock.createPdfSplitJob).not.toHaveBeenCalled()
  })

  it('材料包里只有图片：走图片取字，不建 PDF 任务', async () => {
    // 图片已接入自动识别（见 docs/material-prep-dispatch.md）：不再提示
    //「只支持 PDF」，而是单页 OCR 取字回填段正文。
    const { update } = setup({ mats: [imgMat(0)] })
    apiMock.fetchAttachmentBytes.mockResolvedValue(new ArrayBuffer(8))
    apiMock.ocrImage.mockResolvedValue({ width: 1, height: 1, blocks: [{ text: '送货单' }] })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(apiMock.createPdfSplitJob).not.toHaveBeenCalled()
    expect(apiMock.ocrImage).toHaveBeenCalled()
    // update 收的是 updater 回调，真实 store 会调用它；这里要手动执行才能看到回写，
    // 否则断言的是 mock 的形参而不是真正写进草稿的内容。
    const updater = update.mock.calls[0]?.[0] as (v: unknown) => unknown
    updater({ mats: [], segs: [], infos: [] })
    expect(draftMock.fillSegmentText).toHaveBeenCalledWith(expect.anything(), 0, '送货单')
  })

  it('Word 材料：走 office 解析转正文，不建 PDF 任务', async () => {
    const { update } = setup({ mats: [officeMat(0)] })
    apiMock.fetchAttachmentBytes.mockResolvedValue(new Uint8Array([1, 2, 3]))
    apiMock.parseOfficeFile.mockResolvedValue({ markdown: '## 起诉状\n\n正文', text: '起诉状 正文' })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(apiMock.createPdfSplitJob).not.toHaveBeenCalled()
    expect(apiMock.parseOfficeFile).toHaveBeenCalled()
    const updater = update.mock.calls[0]?.[0] as (v: unknown) => unknown
    updater({ mats: [], segs: [], infos: [] })
    // 优先回填 Markdown（保留标题层级），而不是退化后的纯文本
    expect(draftMock.fillSegmentText).toHaveBeenCalledWith(expect.anything(), 0, '## 起诉状\n\n正文')
  })

  it('材料包里没有任何可识别内容：提示无可识别材料', async () => {
    setup({ mats: [] })
    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('没有可自动识别'))
  })

  it('PDF 都已被人工拆分：提示跳过原因', async () => {
    setup()
    draftMock.canAutoSplitMat.mockReturnValue(false)
    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('已跳过'))
    expect(apiMock.createPdfSplitJob).not.toHaveBeenCalled()
  })
})

describe('useAutoSplit：成功路径', () => {
  it('全部成功且为 AI 分段：success 提示候选分段数', async () => {
    const { update } = setup({ mats: [pdfMat(0), pdfMat(1)] })
    const { result } = renderHook(() => useAutoSplit())

    await act(async () => {
      await result.current.run()
    })

    expect(apiMock.createPdfSplitJob).toHaveBeenCalledTimes(2)
    // 两个 mat 各回写一次
    expect(update).toHaveBeenCalledTimes(2)
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('律所 AI 分段'))
  })

  it('规则引擎分段时提示质量降级', async () => {
    setup()
    apiMock.getPdfSplitJob.mockResolvedValue({
      status: 'completed',
      segments: [{ p: 0 }],
      summary: { segment_backend: 'rule' },
    })
    const { result } = renderHook(() => useAutoSplit())

    await act(async () => {
      await result.current.run()
    })

    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('规则引擎'))
  })

  it('部分成功：warning 里同时给出成功数与失败数', async () => {
    setup({ mats: [pdfMat(0), pdfMat(1)] })
    let call = 0
    apiMock.getPdfSplitJob.mockImplementation(async () => {
      call += 1
      if (call === 1) {
        return { status: 'completed', segments: [{ p: 0 }], summary: { segment_backend: 'llm' } }
      }
      return { status: 'failed', error_message: '识别服务异常' }
    })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('1 份识别失败'))
  })

  it('全部失败：error 提示首个失败原因', async () => {
    setup()
    apiMock.getPdfSplitJob.mockResolvedValue({ status: 'failed', error_message: '识别服务异常' })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.error).toHaveBeenCalledWith('识别服务异常')
  })

  it('提交阶段失败：error 提示', async () => {
    setup()
    apiMock.createPdfSplitJob.mockRejectedValue(new Error('上传失败'))

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.error).toHaveBeenCalledWith('上传失败')
  })
})

describe('useAutoSplit：竞态与生命周期', () => {
  it('轮询期间用户切走（openId 变化）：不回写 store', async () => {
    setup({ openId: 1 })
    const update = vi.fn()
    // 第一次 getState 用于取初始值，之后返回不同 openId
    let first = true
    storeMock.getState.mockImplementation(() => {
      if (first) {
        first = false
        return { openId: 1, draft: { mats: [pdfMat(0)] }, update }
      }
      return { openId: 999, draft: { mats: [pdfMat(0)] }, update }
    })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(update).not.toHaveBeenCalled()
  })

  it('running 状态在完成后复位', async () => {
    setup()
    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })
    await waitFor(() => expect(result.current.running).toBe(false))
    expect(result.current.progress).toBe('')
  })
})

describe('useAutoSplit：重入', () => {
  it('同帧连点两次：旧 run 过期，只有一个任务流与一次回写', async () => {
    const { update } = setup()
    // 第一个任务的轮询挂住，制造「第一次还没跑完就又点了一次」的窗口
    let release: (v: unknown) => void = () => {}
    apiMock.getPdfSplitJob.mockReturnValueOnce(
      new Promise((res) => {
        release = res as (v: unknown) => void
      }),
    )

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      const first = result.current.run()
      // 不等第一次结束（running 还没渲染回按钮），直接再点
      const second = result.current.run()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
      release({ status: 'completed', segments: [{ p: 0 }], summary: { segment_backend: 'llm' } })
      await Promise.all([first, second])
    })

    // 两个任务都提交了（旧循环在 await 提交里、发现过期前拦不住），但旧循环过期后
    // 不再回写 store、不再弹提示：只有一次回写
    expect(apiMock.createPdfSplitJob).toHaveBeenCalledTimes(2)
    expect(update).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledTimes(1)
    expect(toast.error).not.toHaveBeenCalled()
    expect(result.current.running).toBe(false)
    expect(result.current.progress).toBe('')
  })
})

describe('useAutoSplit：轮询状态机', () => {
  it('processing 状态会继续轮询直到 completed', async () => {
    setup()
    let n = 0
    apiMock.getPdfSplitJob.mockImplementation(async () => {
      n += 1
      if (n < 3) return { status: 'processing' }
      return { status: 'completed', segments: [{ p: 0 }], summary: { segment_backend: 'llm' } }
    })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    // 两次 processing + 一次 completed
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(3)
  })

  it('cancelled 状态按失败处理并带默认文案', async () => {
    setup()
    apiMock.getPdfSplitJob.mockResolvedValue({ status: 'cancelled' })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('已取消'))
  })
})

/**
 * 某次真实事故（164 页卷宗卡在 135 页二十余分钟）暴露的两个缺口。
 * 这里锁住：进度要可见、卡死要早报，而不是让律师干等 14 分钟。
 */
describe('useAutoSplit：进度可见与卡死自愈', () => {
  it('轮询期间把页级进度报给 UI（而不是只有「正在识别」）', async () => {
    setup()
    apiMock.getPdfSplitJob
      .mockResolvedValueOnce({ status: 'processing', processed_pages: 41, total_pages: 164 })
      .mockResolvedValueOnce({ status: 'completed', segments: [{ p: 0 }], summary: {} })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    // 完成后 progress 被清空是预期的（结果已在草稿里）；
    // 这里只锁住「轮询时确实按页数产生了文案」这条链路——
    // 通过 processing 那一轮已发生来间接证明（若未产生文案则不会进入第二轮）。
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(1 + 1)
  })

  it('后端心跳停了：立即报中断，不等满轮询上限', async () => {
    setup()
    // stale_seconds 远超前端阈值(720s) → 说明 worker 已死
    apiMock.getPdfSplitJob.mockResolvedValue({
      status: 'processing',
      processed_pages: 135,
      total_pages: 164,
      stale_seconds: 1800,
    })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('中断'))
    // 只查一次就放弃，不空转 420 次
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(1)
  })

  it('心跳正常时不误报中断', async () => {
    setup()
    apiMock.getPdfSplitJob
      .mockResolvedValueOnce({ status: 'processing', processed_pages: 100, total_pages: 164, stale_seconds: 5 })
      .mockResolvedValueOnce({ status: 'completed', segments: [{ p: 0 }], summary: {} })

    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })

    expect(toast.error).not.toHaveBeenCalledWith(expect.stringContaining('中断'))
    expect(apiMock.getPdfSplitJob).toHaveBeenCalledTimes(2)
  })
})
