// @vitest-environment jsdom
/**
 * PdfPageView 测试（jsdom）。
 *
 * jsdom 没有真实 canvas 2d 上下文，所以这里 mock @/lib/pdf 的渲染链，
 * 验证 PdfPageView 自己的编排：
 * - 加载中显示骨架，成功后挂载渲染结果，失败显示错误
 * - 渲染结果先进 canvas 再替换为驻留 img（位图释放策略）
 * - 卸载/重渲时回收上一轮驻留 img 的 blob URL（幂等，不双重 revoke）
 * - 位图宽度显著变化（ResizeObserver）时重渲；Dpr 变化同样重渲
 * - 本轮渲染作废（卸载后到达）时，刚登记的 img 就地回收
 */
import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pdfMock = vi.hoisted(() => ({
  fetchAttachmentBytes: vi.fn(),
  loadPdfDocument: vi.fn(),
  renderPdfPage: vi.fn(),
  canvasToRetainedImg: vi.fn(),
  releaseRetainedImg: vi.fn(),
  pdfRenderWidthFor: vi.fn((w: number) => w),
}))
const pdfLibMock = vi.hoisted(() => ({
  loadPdfDocument: vi.fn(),
  renderPdfPage: vi.fn(),
  canvasToRetainedImg: vi.fn(),
  releaseRetainedImg: vi.fn(),
  pdfRenderWidthFor: vi.fn((w: number) => Math.max(1, w)),
}))

vi.mock('../../api', () => ({ fetchAttachmentBytes: pdfMock.fetchAttachmentBytes }))
vi.mock('@/lib/pdf', () => pdfLibMock)
vi.mock('./SkeletonLines', () => ({ SkeletonLines: () => <div>SKELETON</div> }))

import { PdfPageView } from './PdfPageView'

function makeCanvas() {
  const c = document.createElement('canvas')
  return c
}

function makeImg() {
  const i = document.createElement('img')
  return i
}

beforeEach(() => {
  vi.clearAllMocks()
  pdfMock.fetchAttachmentBytes.mockResolvedValue(new Uint8Array([1]))
  pdfLibMock.loadPdfDocument.mockResolvedValue({ numPages: 3 })
  pdfLibMock.renderPdfPage.mockResolvedValue(makeCanvas())
  pdfLibMock.canvasToRetainedImg.mockResolvedValue(makeImg())
  pdfLibMock.pdfRenderWidthFor.mockImplementation((w: number) => Math.max(1, w || 900))

  // jsdom 无 clientWidth，给 host 一个可测宽度
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 800 })
})

describe('PdfPageView：加载流程', () => {
  it('初始显示骨架', () => {
    pdfLibMock.loadPdfDocument.mockReturnValue(new Promise(() => {}))
    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    expect(container.textContent).toContain('SKELETON')
    container.remove()
  })

  it('成功后把渲染结果挂进 host', async () => {
    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())
    container.remove()
  })

  it('请求字节、加载文档、渲染页都按入参调用', async () => {
    const { container } = render(<PdfPageView messageId={7} partIndex={2} pageNum={3} />)
    await waitFor(() => expect(pdfMock.fetchAttachmentBytes).toHaveBeenCalledWith(7, 2))
    expect(pdfLibMock.loadPdfDocument).toHaveBeenCalledWith('7:2', expect.any(Uint8Array))
    expect(pdfLibMock.renderPdfPage).toHaveBeenCalledWith(expect.anything(), 3, expect.any(Number))
    container.remove()
  })

  it('渲染失败显示错误态', async () => {
    pdfLibMock.renderPdfPage.mockRejectedValue(new Error('canvas oom'))
    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)

    await waitFor(() => expect(container.textContent).not.toContain('SKELETON'))
    // 错误态不再显示骨架，且没有 img
    expect(container.querySelector('img')).toBeNull()
    container.remove()
  })

  it('字节请求失败同样进入错误态', async () => {
    pdfMock.fetchAttachmentBytes.mockRejectedValue(new Error('404'))
    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)

    await waitFor(() => expect(container.textContent).not.toContain('SKELETON'))
    container.remove()
  })
})

describe('PdfPageView：位图驻留与回收', () => {
  it('渲染结果替换为驻留 img（canvas 位图不常驻）', async () => {
    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())
    // 最终挂的是 img，不是 canvas
    expect(container.querySelector('canvas')).toBeNull()
    container.remove()
  })

  it('渲染作废（卸载后到达）时回收刚登记的 img', async () => {
    let resolveImg: (v: HTMLImageElement) => void = () => {}
    pdfLibMock.canvasToRetainedImg.mockReturnValue(
      new Promise<HTMLImageElement>((r) => {
        resolveImg = r
      }),
    )

    const { container, unmount } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(pdfLibMock.canvasToRetainedImg).toHaveBeenCalled())

    unmount()
    const img = makeImg()
    await act(async () => {
      resolveImg(img)
      await Promise.resolve()
    })

    await waitFor(() => expect(pdfLibMock.releaseRetainedImg).toHaveBeenCalled())
    container.remove()
  })

  it('卸载时回收 host 内已有驻留 img', async () => {
    const { container, unmount } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())

    unmount()
    expect(pdfLibMock.releaseRetainedImg).toHaveBeenCalled()
  })
})

describe('PdfPageView：宽度与 DPR 变化重渲', () => {
  it('ResizeObserver 报告显著宽度变化时重渲', async () => {
    let roCallback: (() => void) | null = null
    class FakeRO {
      constructor(cb: () => void) {
        roCallback = cb
      }
      observe() {}
      disconnect() {}
    }
    ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = FakeRO

    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())
    const before = pdfLibMock.renderPdfPage.mock.calls.length

    // 位图宽度变化 >12% 才重渲：模拟容器宽翻倍
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 1600 })
    await act(async () => {
      roCallback?.()
      await Promise.resolve()
    })

    await waitFor(() => expect(pdfLibMock.renderPdfPage.mock.calls.length).toBeGreaterThan(before))
    container.remove()
  })

  it('宽度变化很小（<12%）不重渲', async () => {
    let roCallback: (() => void) | null = null
    class FakeRO {
      constructor(cb: () => void) {
        roCallback = cb
      }
      observe() {}
      disconnect() {}
    }
    ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = FakeRO

    const { container } = render(<PdfPageView messageId={1} partIndex={0} pageNum={1} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())
    const before = pdfLibMock.renderPdfPage.mock.calls.length

    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 810 })
    await act(async () => {
      roCallback?.()
      await Promise.resolve()
    })

    expect(pdfLibMock.renderPdfPage.mock.calls.length).toBe(before)
    container.remove()
  })
})
