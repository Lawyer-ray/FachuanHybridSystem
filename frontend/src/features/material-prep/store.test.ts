/**
 * material-prep store appendFiles 跨包污染回归单测（node 环境）。
 *
 * mock 只打外围副作用层：./api（上传/详情/保存）、@/lib/pdf（文档缓存）、
 * sonner（toast），draft 域逻辑与 store 本体保持真实。
 * 核心回归：appendFiles 的两个 await 期间关 A 开 B，续体必须按 openId
 * 失配静默丢弃，不得把 A 的 detail 覆盖到 B、不得把 A 的材料追加进 B 的草稿。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { appendPackFilesMock, getPackDetailMock, saveDraftMock, clearBytesCacheMock, fetchBytesMock } = vi.hoisted(
  () => ({
    appendPackFilesMock: vi.fn(),
    getPackDetailMock: vi.fn(),
    saveDraftMock: vi.fn(),
    clearBytesCacheMock: vi.fn(),
    fetchBytesMock: vi.fn(),
  }),
)

const { toastMock, loadPdfDocumentMock, clearPdfDocumentsMock } = vi.hoisted(() => ({
  toastMock: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  loadPdfDocumentMock: vi.fn(),
  clearPdfDocumentsMock: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: toastMock }))

vi.mock('./api', () => ({
  appendPackFiles: appendPackFilesMock,
  getPackDetail: getPackDetailMock,
  saveDraft: saveDraftMock,
  clearBytesCache: clearBytesCacheMock,
  fetchAttachmentBytes: fetchBytesMock,
}))

vi.mock('@/lib/pdf', () => ({
  clearPdfDocuments: clearPdfDocumentsMock,
  loadPdfDocument: loadPdfDocumentMock,
}))

import { useReader } from './store'
import type { AttachmentMeta, DraftState, InboxMessageDetail } from './types'

// ---- 夹具 ----

function pdfAtt(over: Partial<AttachmentMeta> = {}): AttachmentMeta {
  return {
    filename: 'a.pdf',
    original_filename: 'a.pdf',
    custom_filename: null,
    size: 100,
    content_type: 'application/pdf',
    part_index: 0,
    ...over,
  } as AttachmentMeta
}

/** 详情夹具：draft_state 传 {} 即「从未进过阅读器」的空占位 */
function detail(id: number, attachments: AttachmentMeta[]): InboxMessageDetail {
  return { id, subject: `pack-${id}`, attachments, status: 'todo', draft_state: {} } as unknown as InboxMessageDetail
}

function draftOf(matCount: number): DraftState {
  const mats = Array.from({ length: matCount }, (_, i) => ({ partIndex: i, n: `a${i}.pdf`, k: 'pdf' as const, pages: 2 }))
  return { mats, segs: [], infos: [] }
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function openPackA() {
  useReader.setState({
    openId: 1,
    detail: detail(1, [pdfAtt({ part_index: 0, page_count: 2 })]),
    draft: draftOf(1),
    status: 'ready',
    error: '',
    closing: false,
  })
}

/** B 包详情：附件 c.pdf 5 页，open() 会据此建初始草稿 */
const packB = () => detail(2, [pdfAtt({ filename: 'c.pdf', original_filename: 'c.pdf', part_index: 0, page_count: 5 })])

beforeEach(() => {
  vi.clearAllMocks()
  loadPdfDocumentMock.mockResolvedValue({ numPages: 3 } as never)
  useReader.setState({
    openId: null,
    detail: null,
    draft: null,
    status: 'idle',
    error: '',
    closing: false,
    pickInfo: -1,
    zoom: 1,
    cols: 1,
    selMode: false,
    selPages: [],
    lastAnchor: -1,
    ocrPending: null,
    assignOpen: false,
  })
})

describe('useReader.appendFiles 跨包守卫', () => {
  it('上传期间关 A 开 B：A 的响应被静默丢弃，B 的 detail/draft 不被污染', async () => {
    openPackA()
    // A 上传完成后的详情：多出 part_index=1 的 b.pdf（3 页）
    const updatedA = detail(1, [
      pdfAtt({ part_index: 0, page_count: 2 }),
      pdfAtt({ filename: 'b.pdf', original_filename: 'b.pdf', part_index: 1, page_count: 3 }),
    ])
    const gate = deferred<InboxMessageDetail>()
    appendPackFilesMock.mockReturnValue(gate.promise)
    getPackDetailMock.mockResolvedValue(packB())

    const pending = useReader.getState().appendFiles([new File(['x'], 'b.pdf')])
    await useReader.getState().open(2) // 上传 pending 期间切到 B 包
    gate.resolve(updatedA)
    await pending

    const s = useReader.getState()
    expect(s.openId).toBe(2)
    expect(s.detail).not.toBe(updatedA) // A 的 detail 没有覆盖到 B
    expect(s.draft?.mats).toEqual([{ partIndex: 0, n: 'c.pdf', k: 'pdf', pages: 5 }]) // B 的初始草稿原样
    expect(toastMock).not.toHaveBeenCalled()
    expect(toastMock.success).not.toHaveBeenCalled()
    expect(toastMock.error).not.toHaveBeenCalled()
  })

  it('附件解析期间关 A 开 B：第二道守卫同样静默丢弃', async () => {
    openPackA()
    // 新附件缺 page_count → resolveMats 走 fetchAttachmentBytes（受控闸门）
    const updatedA = detail(1, [
      pdfAtt({ part_index: 0, page_count: 2 }),
      pdfAtt({ filename: 'b.pdf', original_filename: 'b.pdf', part_index: 1 }),
    ])
    appendPackFilesMock.mockResolvedValue(updatedA)
    getPackDetailMock.mockResolvedValue(packB())
    const gate = deferred<ArrayBuffer>()
    fetchBytesMock.mockReturnValue(gate.promise)

    const pending = useReader.getState().appendFiles([new File(['x'], 'b.pdf')])
    // 等上传响应已过第一道守卫、解析已挂起在 fetch 上
    await vi.waitFor(() => expect(fetchBytesMock).toHaveBeenCalledTimes(1))
    await useReader.getState().open(2) // 解析 pending 期间切到 B 包
    gate.resolve(new ArrayBuffer(8))
    await pending

    const s = useReader.getState()
    expect(s.openId).toBe(2)
    expect(s.detail).not.toBe(updatedA)
    expect(s.draft?.mats).toEqual([{ partIndex: 0, n: 'c.pdf', k: 'pdf', pages: 5 }])
    expect(toastMock).not.toHaveBeenCalled()
    expect(toastMock.success).not.toHaveBeenCalled()
    expect(toastMock.error).not.toHaveBeenCalled()
  })

  it('上传期间阅读器已卸载（openId 置空）：响应同样被静默丢弃', async () => {
    openPackA()
    const updatedA = detail(1, [
      pdfAtt({ part_index: 0, page_count: 2 }),
      pdfAtt({ filename: 'b.pdf', original_filename: 'b.pdf', part_index: 1, page_count: 3 }),
    ])
    const gate = deferred<InboxMessageDetail>()
    appendPackFilesMock.mockReturnValue(gate.promise)

    const pending = useReader.getState().appendFiles([new File(['x'], 'b.pdf')])
    // 模拟 close() 定时器到点后的卸载态（openId/detail/draft 全清）
    useReader.setState({ openId: null, detail: null, draft: null, status: 'idle' })
    gate.resolve(updatedA)
    await pending

    const s = useReader.getState()
    expect(s.openId).toBeNull()
    expect(s.detail).toBeNull()
    expect(s.draft).toBeNull()
    expect(toastMock).not.toHaveBeenCalled()
  })

  it('未切包：正常追加材料并入草稿', async () => {
    openPackA()
    const updatedA = detail(1, [
      pdfAtt({ part_index: 0, page_count: 2 }),
      pdfAtt({ filename: 'b.pdf', original_filename: 'b.pdf', part_index: 1, page_count: 3 }),
    ])
    appendPackFilesMock.mockResolvedValue(updatedA)

    await useReader.getState().appendFiles([new File(['x'], 'b.pdf')])

    const s = useReader.getState()
    expect(s.detail).toBe(updatedA)
    expect(s.draft?.mats).toHaveLength(2)
    expect(s.draft?.mats[1]).toEqual({ partIndex: 1, n: 'b.pdf', k: 'pdf', pages: 3 })
    expect(toastMock.success).toHaveBeenCalledWith('已追加 1 份材料')
  })
})

describe('useReader.removeInfo 取字态下标同步', () => {
  /** 三字段草稿：取字态默认指向 infos[2]（对方当事人） */
  function openWithInfos() {
    const draft = draftOf(1)
    draft.infos = [
      { k: '委托人', v: '张三', src: '', srcRef: null },
      { k: '标的额', v: '', src: '', srcRef: null },
      { k: '对方当事人', v: '李四', src: '', srcRef: null },
    ]
    useReader.setState({ openId: 1, detail: detail(1, []), draft, status: 'ready' })
    useReader.getState().setPickInfo(2)
  }

  it('删除取字字段之前的字段：pickInfo 随数组前移 -1，仍指向原字段', () => {
    openWithInfos()
    useReader.getState().removeInfo(0) // 删掉 infos[0] 委托人
    const s = useReader.getState()
    expect(s.draft?.infos.map((f) => f.k)).toEqual(['标的额', '对方当事人'])
    expect(s.pickInfo).toBe(1) // 仍指向 对方当事人
  })

  it('删除的正是取字字段：退出取字态（pickInfo=-1，ocrPending 清空）', () => {
    openWithInfos()
    useReader.setState({ ocrPending: { mi: 0, p: 1, rect: { x: 0, y: 0, w: 0.1, h: 0.1 }, text: '', loading: false } })
    useReader.getState().removeInfo(2)
    const s = useReader.getState()
    expect(s.draft?.infos).toHaveLength(2)
    expect(s.pickInfo).toBe(-1)
    expect(s.ocrPending).toBeNull()
  })

  it('删除取字字段之后的字段：pickInfo 不动；非取字态删除：pickInfo 保持 -1', () => {
    openWithInfos()
    useReader.getState().setPickInfo(1) // 取字指向 标的额
    useReader.getState().removeInfo(2) // 删掉它之后的 对方当事人
    expect(useReader.getState().pickInfo).toBe(1)
    expect(useReader.getState().draft?.infos.map((f) => f.k)).toEqual(['委托人', '标的额'])

    useReader.getState().setPickInfo(-1)
    useReader.getState().removeInfo(0)
    expect(useReader.getState().pickInfo).toBe(-1)
    expect(useReader.getState().draft?.infos.map((f) => f.k)).toEqual(['标的额'])
  })
})
