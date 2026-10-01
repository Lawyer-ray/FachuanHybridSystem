import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// mock pdfjs-dist：单测只关心 pdf.ts 对 getDocument 的调用契约（副本传参 / wasmUrl / 缓存语义），
// 不渲染真实 PDF。
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}))

import { getDocument } from 'pdfjs-dist'
import {
  PDF_RENDER_MAX_WIDTH,
  PDF_RENDER_WIDTH,
  clearPdfDocuments,
  loadPdfDocument,
  pdfRenderWidthFor,
} from './pdf'

function makeTask(numPages = 3) {
  return { promise: Promise.resolve({ numPages }), destroy: vi.fn().mockResolvedValue(undefined) }
}

beforeEach(() => {
  vi.mocked(getDocument).mockReset()
  clearPdfDocuments()
})

afterEach(() => {
  clearPdfDocuments()
})

describe('pdfRenderWidthFor（DPR 感知的渲染宽度）', () => {
  it('CSS 宽 × DPR：Retina 单列 900 → 1800', () => {
    expect(pdfRenderWidthFor(900, 2)).toBe(1800)
  })

  it('DPR=1 最低超采样 1.5x：外接屏也有余量（900 → 1350）', () => {
    expect(pdfRenderWidthFor(900, 1)).toBe(1350)
  })

  it('DPR 封顶 2：3x 屏不翻倍（960×2 → 1920 上限内）', () => {
    expect(pdfRenderWidthFor(960, 3)).toBe(1920)
  })

  it('下限保底 PDF_RENDER_WIDTH：窄列多列布局也有基础清晰度', () => {
    expect(pdfRenderWidthFor(320, 2)).toBe(PDF_RENDER_WIDTH)
    expect(pdfRenderWidthFor(140, 1)).toBe(PDF_RENDER_WIDTH)
  })

  it('上限封顶：超宽页（zoom 大）不超 PDF_RENDER_MAX_WIDTH', () => {
    expect(pdfRenderWidthFor(2000, 2)).toBe(PDF_RENDER_MAX_WIDTH)
  })
})

describe('loadPdfDocument（#501 wasmUrl + 缓存回归）', () => {
  it('传给 pdf.js 的是 buffer 副本（本体不被 transfer 废掉），且带 wasmUrl', () => {
    const task = makeTask()
    vi.mocked(getDocument).mockReturnValue(task as never)
    const data = new Uint8Array([1, 2, 3, 4]).buffer

    loadPdfDocument('m1:p0', data)

    expect(getDocument).toHaveBeenCalledTimes(1)
    const params = vi.mocked(getDocument).mock.calls[0]![0] as { data: ArrayBuffer; wasmUrl: string }
    // 副本：内容相同但不是同一个 buffer 对象，调用方后续仍可安全复用本体
    expect(params.data).not.toBe(data)
    expect(new Uint8Array(params.data)).toEqual(new Uint8Array(data))
    // wasmUrl 是 6.x 扫描件双图层解码的硬前提，缺失会静默丢文字层
    expect(params.wasmUrl).toMatch(/pdfjs\/$/)
  })

  it('同 key 复用缓存：并发/重复调用只 getDocument 一次、拿到同一 promise', async () => {
    const task = makeTask()
    vi.mocked(getDocument).mockReturnValue(task as never)

    const p1 = loadPdfDocument('m1:p0', new ArrayBuffer(4))
    const p2 = loadPdfDocument('m1:p0', new ArrayBuffer(4))

    expect(p1).toBe(p2)
    expect(getDocument).toHaveBeenCalledTimes(1)
    await expect(p1).resolves.toMatchObject({ numPages: 3 })
  })

  it('不同 key 各自独立缓存（多 PDF 材料包并发打开场景）', async () => {
    const t1 = makeTask(3)
    const t2 = makeTask(9)
    vi.mocked(getDocument).mockReturnValueOnce(t1 as never).mockReturnValueOnce(t2 as never)

    const [d1, d2] = await Promise.all([
      loadPdfDocument('m1:p0', new ArrayBuffer(4)),
      loadPdfDocument('m1:p1', new ArrayBuffer(4)),
    ])
    expect(d1.numPages).toBe(3)
    expect(d2.numPages).toBe(9)
    expect(getDocument).toHaveBeenCalledTimes(2)
  })

  it('加载失败清除该 key 缓存，重试会重新 getDocument', async () => {
    const fail = { promise: Promise.reject(new Error('bad pdf')), destroy: vi.fn() }
    vi.mocked(getDocument).mockReturnValueOnce(fail as never)

    const p = loadPdfDocument('m1:p0', new ArrayBuffer(4))
    await expect(p).rejects.toThrow('bad pdf')
    await Promise.resolve().then(() => {}) // 等 catch 回调清缓存

    const ok = makeTask()
    vi.mocked(getDocument).mockReturnValueOnce(ok as never)
    await expect(loadPdfDocument('m1:p0', new ArrayBuffer(4))).resolves.toMatchObject({ numPages: 3 })
    expect(getDocument).toHaveBeenCalledTimes(2)
  })
})

describe('clearPdfDocuments', () => {
  it('销毁全部缓存任务的 worker，清空后再加载会重新建任务', async () => {
    const t1 = makeTask()
    const t2 = makeTask()
    vi.mocked(getDocument).mockReturnValueOnce(t1 as never).mockReturnValueOnce(t2 as never)
    loadPdfDocument('a', new ArrayBuffer(4))
    loadPdfDocument('b', new ArrayBuffer(4))

    clearPdfDocuments()

    expect(t1.destroy).toHaveBeenCalledTimes(1)
    expect(t2.destroy).toHaveBeenCalledTimes(1)
    const again = makeTask()
    vi.mocked(getDocument).mockReturnValueOnce(again as never)
    await loadPdfDocument('a', new ArrayBuffer(4))
    expect(getDocument).toHaveBeenCalledTimes(3)
  })
})
