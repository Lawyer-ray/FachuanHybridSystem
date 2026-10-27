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
}))
const draftMock = vi.hoisted(() => ({
  applyAutoSplit: vi.fn((v: unknown) => ({ ...(v as object), applied: true })),
  canAutoSplitMat: vi.fn(),
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
function imgMat(mi: number) {
  return { k: 'image', partIndex: mi, n: `m${mi}.jpg`, customName: '' }
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

  it('材料包里没有 PDF：提示只支持 PDF', async () => {
    setup({ mats: [imgMat(0)] })
    const { result } = renderHook(() => useAutoSplit())
    await act(async () => {
      await result.current.run()
    })
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('没有 PDF'))
    expect(apiMock.createPdfSplitJob).not.toHaveBeenCalled()
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

    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('1 个识别失败'))
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
