// @vitest-environment jsdom
/**
 * lib/pdf 的 canvas 渲染族单测（jsdom）。
 *
 * pdf.test.ts 已覆盖 pdfRenderWidthFor / loadPdfDocument 缓存 / 驻留 img 登记，
 * 本文件补齐 DOM 依赖部分：renderPdfPage(+Region)、imageRegionBlob、canvasToBlob、
 * clearPdfCache 别名。jsdom 的 canvas 2d 上下文不可用，document.createElement
 * 用可控行为的替身桩（getContext/toBlob/尺寸断言），pdfjs mock 提供 page/viewport。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}))

import { getDocument } from 'pdfjs-dist'
import {
  canvasToBlob,
  clearPdfCache,
  imageRegionBlob,
  loadPdfDocument,
  renderPdfPage,
  renderPdfPageRegion,
} from './pdf'

/** 2d 上下文桩：只记录绘制调用 */
function makeCtx() {
  return {
    fillStyle: '',
    fillRect: vi.fn(),
    drawImage: vi.fn(),
  }
}

/** canvas 替身：可注 getContext 结果与 toBlob 行为 */
function fakeCanvas(opts: { ctx: ReturnType<typeof makeCtx> | null } = { ctx: makeCtx() }) {
  return {
    width: 0,
    height: 0,
    getContext: (_type?: string) => opts.ctx,
    toBlob: (cb: (b: Blob | null) => void) => cb(new Blob(['png-bytes'], { type: 'image/png' })),
  }
}

let realCreate: typeof document.createElement

beforeEach(() => {
  vi.clearAllMocks()
  realCreate = document.createElement.bind(document)
})

afterEach(() => {
  vi.restoreAllMocks()
  clearPdfCache()
})

/** 让 document.createElement('canvas') 返回替身（其余标签走真实实现） */
function stubCanvasFactory(make: () => unknown) {
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string) =>
    tag === 'canvas' ? (make() as never) : realCreate(tag)) as never)
}

/** 900x1200 比例（scale=1 时 600x800）的页桩 */
function pdfPageStub() {
  return {
    getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
    render: vi.fn(() => ({ promise: Promise.resolve() })),
  }
}

/** 900x1200 比例（scale=1 时 600x800）的页桩；getPage 多次调用返回同一实例 */
function pdfStub() {
  const page = pdfPageStub()
  return { getPage: vi.fn(async () => page), __page: page } as never
}

describe('renderPdfPage', () => {
  it('按 targetWidth 求缩放、位图尺寸取整、render 收到同一 canvas', async () => {
    let canvas!: ReturnType<typeof fakeCanvas>
    stubCanvasFactory(() => (canvas = fakeCanvas()))
    const pdf = pdfStub()

    const got = await renderPdfPage(pdf, 1, 900)

    expect(got).toBe(canvas)
    expect(canvas.width).toBe(900)
    expect(canvas.height).toBe(1200)
    const page = (pdf as { __page: ReturnType<typeof pdfPageStub> }).__page
    expect(page.render).toHaveBeenCalledWith({ canvas, viewport: { width: 900, height: 1200 } })
  })

  it('ctx 不可用（极老浏览器/内存耗尽）→ 抛「无法创建 canvas 2d 上下文」', async () => {
    stubCanvasFactory(() => fakeCanvas({ ctx: null }))
    await expect(renderPdfPage(pdfStub(), 1, 900)).rejects.toThrow('无法创建 canvas 2d 上下文')
  })
})

describe('renderPdfPageRegion（裁剪 + 留白）', () => {
  it('目标矩形按全图比例裁出，四周留 pad，白底填充后 drawImage', async () => {
    const canvases: Array<ReturnType<typeof fakeCanvas>> = []
    stubCanvasFactory(() => {
      const c = fakeCanvas()
      canvases.push(c)
      return c
    })
    // 全图 900x1200（targetWidth 900），rect 中心区 50%
    const canvas = await renderPdfPageRegion(pdfStub(), 1, { x: 0.2, y: 0.2, w: 0.5, h: 0.5 }, 900)

    const [full, region] = canvases
    expect(full!.width).toBe(900)
    // cw=450、ch=600，pad=round(900*0.02)=18：画布 = 裁剪区 + 两侧留白
    expect(region!.width).toBe(450 + 36)
    expect(region!.height).toBe(600 + 36)
    const ctx = region!.getContext('2d') as ReturnType<typeof makeCtx>
    expect(ctx.fillStyle).toBe('#ffffff')
    expect(ctx.fillRect).toHaveBeenCalledWith(0, 0, region!.width, region!.height)
    // 源起点 = rect 左上角内缩一个 pad：sx=0.2*900-18=162、sy=0.2*1200-18=222
    expect(ctx.drawImage).toHaveBeenCalledWith(full, 162, 222, region!.width, region!.height, 0, 0, region!.width, region!.height)
    expect(canvas).toBe(region)
  })

  it('极小矩形保底 32px；起点不越过原图边界（max 0 钳制）', async () => {
    const canvases: Array<ReturnType<typeof fakeCanvas>> = []
    stubCanvasFactory(() => {
      const c = fakeCanvas()
      canvases.push(c)
      return c
    })
    await renderPdfPageRegion(pdfStub(), 1, { x: 0, y: 0, w: 0.001, h: 0.001 }, 900)

    const [, region] = canvases
    // cw/ch 触发 32px 下限：画布 = 32 + 两侧 pad
    expect(region!.width).toBe(32 + 36)
    expect(region!.height).toBe(32 + 36)
    const ctx = region!.getContext('2d') as ReturnType<typeof makeCtx>
    // rect.x=0 → sx = max(0, -18) = 0
    expect(ctx.drawImage).toHaveBeenCalledWith(canvases[0], 0, 0, region!.width, region!.height, 0, 0, region!.width, region!.height)
  })
})

/** 劫持 new Image()：让 imageRegionBlob 拿到可控行为（宽高/解码成败） */
function stubImageWith(impl: new () => unknown) {
  const realImage = globalThis.Image
  vi.stubGlobal('Image', impl)
  return () => vi.stubGlobal('Image', realImage)
}

describe('imageRegionBlob（图片字节裁剪）', () => {
  let createObjectURL: ReturnType<typeof vi.fn>
  let revokeObjectURL: ReturnType<typeof vi.fn>

  beforeEach(() => {
    let seq = 0
    createObjectURL = vi.fn(() => `blob:img-${seq++}`)
    revokeObjectURL = vi.fn()
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
  })

  afterEach(() => {
    const urlCtor = URL as unknown as Record<string, unknown>
    delete urlCtor.createObjectURL
    delete urlCtor.revokeObjectURL
  })

  it('解码 → 裁剪 → toBlob PNG，finally 撤销 ObjectURL', async () => {
    stubCanvasFactory(() => fakeCanvas())
    // src setter 触发异步 onload
    const restore = stubImageWith(
      class {
        width = 400
        height = 300
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        private _src = ''
        get src() {
          return this._src
        }
        set src(v: string) {
          this._src = v
          queueMicrotask(() => this.onload?.())
        }
      },
    )
    try {
      const blob = await imageRegionBlob(new ArrayBuffer(4), { x: 0.25, y: 0.25, w: 0.5, h: 0.5 })
      expect(blob).toBeInstanceOf(Blob)
      expect(createObjectURL).toHaveBeenCalledTimes(1)
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:img-0')
    } finally {
      restore()
    }
  })

  it('图片解码失败：抛「图片解码失败」，ObjectURL 仍被撤销', async () => {
    stubCanvasFactory(() => fakeCanvas())
    const restore = stubImageWith(
      class {
        width = 0
        height = 0
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        private _src = ''
        get src() {
          return this._src
        }
        set src(v: string) {
          this._src = v
          queueMicrotask(() => this.onerror?.())
        }
      },
    )
    try {
      await expect(imageRegionBlob(new ArrayBuffer(4), { x: 0, y: 0, w: 1, h: 1 })).rejects.toThrow('图片解码失败')
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:img-0')
    } finally {
      restore()
    }
  })

  it('ctx 不可用 → 抛「无法创建 canvas 2d 上下文」', async () => {
    const restore = stubImageWith(
      class {
        width = 100
        height = 100
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        private _src = ''
        get src() {
          return this._src
        }
        set src(v: string) {
          this._src = v
          queueMicrotask(() => this.onload?.())
        }
      },
    )
    stubCanvasFactory(() => fakeCanvas({ ctx: null }))
    try {
      await expect(imageRegionBlob(new ArrayBuffer(4), { x: 0, y: 0, w: 1, h: 1 })).rejects.toThrow('无法创建 canvas 2d 上下文')
    } finally {
      restore()
    }
  })
})

describe('canvasToBlob', () => {
  it('toBlob 回调有 blob → resolve；回调 null → 拒绝「PNG 编码失败」', async () => {
    stubCanvasFactory(() => fakeCanvas())
    const blob = await canvasToBlob(fakeCanvas() as unknown as HTMLCanvasElement)
    expect(blob).toBeInstanceOf(Blob)

    const bad = {
      toBlob: (cb: (b: Blob | null) => void) => cb(null),
      getContext: () => null,
      width: 0,
      height: 0,
    }
    await expect(canvasToBlob(bad as unknown as HTMLCanvasElement)).rejects.toThrow('PNG 编码失败')
  })
})

describe('clearPdfCache（登出全局清理入口）', () => {
  it('与 clearPdfDocuments 同语义：销毁缓存任务的 worker', async () => {
    const task = { promise: Promise.resolve({ numPages: 1 }), destroy: vi.fn().mockResolvedValue(undefined) }
    vi.mocked(getDocument).mockReturnValue(task as never)

    await loadPdfDocument('k1', new ArrayBuffer(4))
    clearPdfCache()

    expect(task.destroy).toHaveBeenCalledTimes(1)
  })
})
