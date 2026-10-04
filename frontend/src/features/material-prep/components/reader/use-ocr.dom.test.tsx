// @vitest-environment jsdom
/**
 * useReaderOcr（标来源 ⇒ 框选 ⇒ RapidOCR）单测（jsdom）。
 *
 * mock 只打外围副作用层：@/lib/pdf 的渲染 / 编码原语、../../api 的取字节与
 * OCR 上传、sonner toast。useReader store 与 draft 纯函数保持真实，覆盖
 * pickPage 记来源、pdf / photo / office 三条取字路径、失败兜底与 ocrOk 确认回填。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { toastMock, bytesMock, ocrMock, saveDraftMock, loadDocMock, renderRegionMock, canvasBlobMock, imageRegionMock } =
  vi.hoisted(() => ({
    toastMock: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
    bytesMock: vi.fn(),
    ocrMock: vi.fn(),
    saveDraftMock: vi.fn(),
    loadDocMock: vi.fn(),
    renderRegionMock: vi.fn(),
    canvasBlobMock: vi.fn(),
    imageRegionMock: vi.fn(),
  }))

vi.mock('sonner', () => ({ toast: toastMock }))

// 拦掉 pdfjs：渲染 / 编码原语全部替换为桩（store.resetAll 用到的清理函数一并提供）
vi.mock('@/lib/pdf', () => ({
  clearPdfDocuments: vi.fn(),
  clearPdfCache: vi.fn(),
  loadPdfDocument: loadDocMock,
  renderPdfPageRegion: renderRegionMock,
  canvasToBlob: canvasBlobMock,
  imageRegionBlob: imageRegionMock,
}))

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>()
  return {
    ...actual,
    fetchAttachmentBytes: bytesMock,
    ocrImage: ocrMock,
    // update 防抖落盘打到的是 mock，测试环境零网络
    saveDraft: saveDraftMock,
  }
})

import type { BundleMat, DraftState } from '../../types'
import { useReader } from '../../store'

import { useReaderOcr } from './use-ocr'

const RECT = { x: 0.1, y: 0.2, w: 0.3, h: 0.4 }
const docStub = { numPages: 3 } as never
const canvasStub = {} as never

/** 两块 OCR 命中；连接符差异（pdf 换行 / photo 空格）是断言点 */
const ocrBlocks = [
  { x: 0, y: 0, w: 0.5, h: 0.1, text: '甲方', score: 0.9 },
  { x: 0, y: 0.2, w: 0.5, h: 0.1, text: '乙方', score: 0.9 },
]

function makeDraft(mats: BundleMat[]): DraftState {
  return { mats, segs: [], infos: [{ k: '委托人', v: '', src: '', srcRef: null }] }
}

const mat = (over: Partial<BundleMat> & Pick<BundleMat, 'k'>): BundleMat => ({
  partIndex: 0,
  n: '材料.pdf',
  pages: 3,
  ...over,
})

/** setState 首个重载收 Partial；ReturnType 推导避免依赖未导出的 ReaderState */
function setState(partial: Partial<ReturnType<typeof useReader.getState>>) {
  act(() => {
    useReader.setState(partial)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  saveDraftMock.mockResolvedValue(undefined)
  useReader.getState().resetAll()
})

afterEach(() => {
  useReader.getState().resetAll()
})

describe('pickPage 点页记来源', () => {
  it('未进入取字（pickInfo=-1）：点页无任何写入、不弹 toast', () => {
    setState({ openId: 5, draft: makeDraft([mat({ k: 'pdf' })]), pickInfo: -1 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.pickPage(0, 2)
    })
    const info = useReader.getState().draft?.infos[0]
    expect(info).toMatchObject({ v: '', src: '', srcRef: null })
    expect(useReader.getState().pickInfo).toBe(-1)
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('记来源：src 用材料名（customName 优先）+ 页码，srcRef 落页坐标，pickInfo 复位', () => {
    setState({
      openId: 5,
      draft: makeDraft([mat({ k: 'pdf', customName: '委托合同' })]),
      pickInfo: 0,
    })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.pickPage(0, 2)
    })
    expect(useReader.getState().draft?.infos[0]).toMatchObject({
      src: '委托合同 第 2 页',
      srcRef: { mi: 0, p: 2 },
    })
    expect(useReader.getState().pickInfo).toBe(-1)
    expect(toastMock.success).toHaveBeenCalledWith('已记来源：委托合同 第 2 页')
  })
})

describe('onOcrBox 框选取字', () => {
  it('未进入取字（pickInfo=-1）：拖框不触发任何取字请求', () => {
    setState({ openId: 5, draft: makeDraft([mat({ k: 'pdf' })]), pickInfo: -1 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })
    expect(bytesMock).not.toHaveBeenCalled()
    expect(ocrMock).not.toHaveBeenCalled()
    expect(useReader.getState().ocrPending).toBeNull()
  })

  it('pdf 路径全链路：loading 中间态 → 取字节 / 载文档 / 渲染区域 / OCR，文字块按行拼接', async () => {
    const buf = new ArrayBuffer(8)
    const blob = new Blob(['png'])
    bytesMock.mockResolvedValue(buf)
    loadDocMock.mockResolvedValue(docStub)
    renderRegionMock.mockResolvedValue(canvasStub)
    canvasBlobMock.mockResolvedValue(blob)
    let resolveOcr!: (v: { width: number; height: number; blocks: typeof ocrBlocks }) => void
    ocrMock.mockReturnValue(
      new Promise((resolve) => {
        resolveOcr = resolve
      }),
    )
    setState({ openId: 5, draft: makeDraft([mat({ k: 'pdf', partIndex: 0 })]), pickInfo: 0 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })

    // 前置链路全走完、卡在 OCR 上：pending 处于 loading
    await waitFor(() => expect(ocrMock).toHaveBeenCalled())
    expect(useReader.getState().ocrPending).toMatchObject({ mi: 0, p: 1, loading: true, text: '' })
    expect(bytesMock).toHaveBeenCalledWith(5, 0)
    expect(loadDocMock).toHaveBeenCalledWith('5:0', buf)
    expect(renderRegionMock).toHaveBeenCalledWith(docStub, 1, RECT)
    expect(canvasBlobMock).toHaveBeenCalledWith(canvasStub)
    expect(ocrMock).toHaveBeenCalledWith(blob)

    resolveOcr({ width: 100, height: 50, blocks: ocrBlocks })
    await waitFor(() =>
      expect(useReader.getState().ocrPending).toEqual({
        mi: 0,
        p: 1,
        rect: RECT,
        text: '甲方\n乙方',
        loading: false,
      }),
    )
  })

  it('photo 路径：字节裁图后直接 OCR，文字块以空格拼接（不走 pdf 渲染链）', async () => {
    const buf = new ArrayBuffer(4)
    const blob = new Blob(['img'])
    bytesMock.mockResolvedValue(buf)
    imageRegionMock.mockResolvedValue(blob)
    ocrMock.mockResolvedValue({ width: 100, height: 50, blocks: ocrBlocks })
    setState({ openId: 5, draft: makeDraft([mat({ k: 'photo', n: '现场.jpg' })]), pickInfo: 0 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })
    await waitFor(() => expect(useReader.getState().ocrPending?.loading).toBe(false))
    expect(imageRegionMock).toHaveBeenCalledWith(buf, RECT)
    expect(loadDocMock).not.toHaveBeenCalled()
    expect(renderRegionMock).not.toHaveBeenCalled()
    expect(useReader.getState().ocrPending).toMatchObject({ text: '甲方 乙方' })
  })

  it('office 路径：明确提示不支持逐页取字，pending 落 loading=false 且零 OCR 请求', async () => {
    setState({ openId: 5, draft: makeDraft([mat({ k: 'office', n: '起诉状.docx' })]), pickInfo: 0 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })
    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    expect(toastMock).toHaveBeenCalledWith('Word / Excel 暂不支持逐页取字，已在右栏记下来源页码')
    expect(ocrMock).not.toHaveBeenCalled()
    expect(useReader.getState().ocrPending).toEqual({ mi: 0, p: 1, rect: RECT, text: '', loading: false })
  })

  it('OCR 失败：pending 复位为空文本 + toast.error 提示可重框', async () => {
    bytesMock.mockResolvedValue(new ArrayBuffer(4))
    imageRegionMock.mockResolvedValue(new Blob(['img']))
    ocrMock.mockRejectedValue(new Error('OCR 服务超时'))
    setState({ openId: 5, draft: makeDraft([mat({ k: 'photo' })]), pickInfo: 0 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(toastMock.error).toHaveBeenCalledWith('OCR 识别失败，可重框或手打')
    expect(useReader.getState().ocrPending).toMatchObject({ text: '', loading: false })
  })

  it('防御分支：无 draft 直接返回；mi 越界清空 pending（都不发 OCR 请求）', async () => {
    setState({ openId: 5, draft: null, pickInfo: 0 })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.onOcrBox(0, 1, RECT)
    })
    expect(useReader.getState().ocrPending).toBeNull()
    expect(bytesMock).not.toHaveBeenCalled()

    setState({ draft: makeDraft([mat({ k: 'pdf' })]) })
    act(() => {
      result.current.onOcrBox(5, 1, RECT)
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(useReader.getState().ocrPending).toBeNull()
    expect(ocrMock).not.toHaveBeenCalled()
  })
})

describe('ocrOk 确认回填', () => {
  it('无 pending：no-op（不写 draft、不弹 toast）', () => {
    setState({
      openId: 5,
      draft: makeDraft([mat({ k: 'pdf' })]),
      pickInfo: 0,
      ocrPending: null,
    })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.ocrOk()
    })
    expect(useReader.getState().draft?.infos[0]).toMatchObject({ v: '', src: '' })
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('确认：来源（带框选矩形）与 trim 后文本一并写入目标便签，状态复位并提示字段名', () => {
    setState({
      openId: 5,
      draft: makeDraft([mat({ k: 'pdf' })]),
      pickInfo: 0,
      ocrPending: { mi: 0, p: 2, rect: RECT, text: ' 甲方（王五） ', loading: false },
    })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.ocrOk()
    })
    expect(useReader.getState().draft?.infos[0]).toEqual({
      k: '委托人',
      v: '甲方（王五）',
      src: '材料.pdf 第 2 页',
      srcRef: { mi: 0, p: 2, rect: RECT },
    })
    expect(useReader.getState().pickInfo).toBe(-1)
    expect(useReader.getState().ocrPending).toBeNull()
    expect(toastMock.success).toHaveBeenCalledWith('已填入「委托人」')
  })

  it('识别文本为空白：只标来源、不覆写已有值', () => {
    setState({
      openId: 5,
      draft: { mats: [mat({ k: 'pdf' })], segs: [], infos: [{ k: '委托人', v: '手打的值', src: '', srcRef: null }] },
      pickInfo: 0,
      ocrPending: { mi: 0, p: 1, rect: RECT, text: '   ', loading: false },
    })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.ocrOk()
    })
    expect(useReader.getState().draft?.infos[0]).toMatchObject({
      v: '手打的值',
      src: '材料.pdf 第 1 页',
    })
  })

  it('pickInfo 已退出（di<0）：清掉 pending 与取字态，但不写任何便签', () => {
    setState({
      openId: 5,
      draft: makeDraft([mat({ k: 'pdf' })]),
      pickInfo: -1,
      ocrPending: { mi: 0, p: 1, rect: RECT, text: '甲', loading: false },
    })
    const { result } = renderHook(() => useReaderOcr())
    act(() => {
      result.current.ocrOk()
    })
    expect(useReader.getState().ocrPending).toBeNull()
    expect(useReader.getState().pickInfo).toBe(-1)
    expect(useReader.getState().draft?.infos[0]).toMatchObject({ v: '', src: '' })
  })
})
