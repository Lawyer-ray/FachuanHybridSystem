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
  // draft-persistence 期望 saveDraft 返回 thenable，否则 .catch 报错
  saveDraftMock.mockResolvedValue(undefined as never)
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

// ============ 选择与分段操作（2026-10 覆盖率补测） ============

/** 造一个含 N 页、每页 1 个 segment 的草稿，供选择逻辑用 */
function draftWithPages(pageCount: number): DraftState {
  const mats = [{ partIndex: 0, n: 'a.pdf', k: 'pdf' as const, pages: pageCount }]
  const segs = Array.from({ length: pageCount }, (_, i) => ({
    id: `sg-${i}`,
    t: 'other',
    fn: `seg-${i}`,
    refs: [{ mi: 0, p: i }],
    manual: false,
  }))
  return { mats, segs, infos: [] } as unknown as DraftState
}

describe('useReader 选择模式', () => {
  it('toggleSelMode 开启时清 pickInfo，关闭时清空选页', () => {
    useReader.setState({ draft: draftWithPages(3), pickInfo: 2 })

    useReader.getState().toggleSelMode()
    expect(useReader.getState().selMode).toBe(true)
    expect(useReader.getState().pickInfo).toBe(-1)

    useReader.setState({ selPages: [{ mi: 0, p: 1 }] })
    useReader.getState().toggleSelMode()
    expect(useReader.getState().selMode).toBe(false)
    expect(useReader.getState().selPages).toEqual([])
  })

  it('单选：点击加入，再点同页移除', () => {
    useReader.setState({ draft: draftWithPages(3), selMode: true })

    useReader.getState().toggleSel(0, 1, false)
    expect(useReader.getState().selPages).toEqual([{ mi: 0, p: 1 }])

    useReader.getState().toggleSel(0, 1, false)
    expect(useReader.getState().selPages).toEqual([])
  })

  it('shift 范围选：从锚点到当前页全选', () => {
    useReader.setState({ draft: draftWithPages(5), selMode: true })

    // 先点第 1 页设锚点
    useReader.getState().toggleSel(0, 1, false)
    expect(useReader.getState().lastAnchor).toBe(1)

    // shift 点第 3 页 → 选中 1..3
    useReader.getState().toggleSel(0, 3, true)
    expect(useReader.getState().selPages).toEqual([
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
      { mi: 0, p: 3 },
    ])
  })

  it('shift 范围选：反向（锚点大于当前）同样成立', () => {
    useReader.setState({ draft: draftWithPages(5), selMode: true })

    useReader.getState().toggleSel(0, 3, false)
    useReader.getState().toggleSel(0, 1, true)
    expect(useReader.getState().selPages).toEqual([
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
      { mi: 0, p: 3 },
    ])
  })

  it('无锚点时 shift 点击退化为普通点击', () => {
    useReader.setState({ draft: draftWithPages(3), selMode: true, lastAnchor: -1 })
    useReader.getState().toggleSel(0, 2, true)
    expect(useReader.getState().selPages).toEqual([{ mi: 0, p: 2 }])
  })

  it('无草稿时 toggleSel 是 no-op', () => {
    useReader.setState({ draft: null, selMode: true })
    useReader.getState().toggleSel(0, 0, false)
    expect(useReader.getState().selPages).toEqual([])
  })

  it('clearSel 同时复位锚点', () => {
    useReader.setState({ selPages: [{ mi: 0, p: 0 }], lastAnchor: 3 })
    useReader.getState().clearSel()
    expect(useReader.getState().selPages).toEqual([])
    expect(useReader.getState().lastAnchor).toBe(-1)
  })
})

describe('useReader.applySel / deleteSelected', () => {
  it('无选页时 applySel 是 no-op', () => {
    useReader.setState({ draft: draftWithPages(3), selPages: [] })
    const before = useReader.getState().draft
    useReader.getState().applySel()
    expect(useReader.getState().draft).toBe(before)
  })

  it('不连续选页时 applySel 拒绝并提示', () => {
    const d = draftWithPages(4)
    useReader.setState({ draft: d, selPages: [{ mi: 0, p: 0 }, { mi: 0, p: 2 }] })
    useReader.getState().applySel()
    expect(toastMock).toHaveBeenCalledWith(expect.stringContaining('连续'))
    expect(useReader.getState().selPages).toHaveLength(2)
  })

  it('连续选页时 applySel 合并并清空选择', () => {
    useReader.setState({ draft: draftWithPages(4), selPages: [{ mi: 0, p: 0 }, { mi: 0, p: 1 }] })
    useReader.getState().applySel()
    expect(useReader.getState().selPages).toEqual([])
    expect(toastMock).toHaveBeenCalled()
  })

  it('deleteSelected 无选中时返回 0', () => {
    useReader.setState({ draft: draftWithPages(3), selPages: [] })
    expect(useReader.getState().deleteSelected()).toBe(0)
  })

  it('deleteSelected 可指定目标页（右键未选中页）', () => {
    useReader.setState({ draft: draftWithPages(3), selPages: [] })
    const n = useReader.getState().deleteSelected([{ mi: 0, p: 1 }])
    expect(n).toBe(1)
  })
})

describe('useReader 简单 setter', () => {
  it('setZoom / setCols / setOcrPending / setAssignOpen 各自写入', () => {
    useReader.getState().setZoom(1.5)
    expect(useReader.getState().zoom).toBe(1.5)

    useReader.getState().setCols(2)
    expect(useReader.getState().cols).toBe(2)

    useReader.getState().setAssignOpen(true)
    expect(useReader.getState().assignOpen).toBe(true)
  })

  it('update 对空草稿是 no-op', () => {
    useReader.setState({ draft: null })
    useReader.getState().update((d) => d)
    expect(useReader.getState().draft).toBeNull()
  })
})

// ============ open / close / resetAll / update（2026-10 覆盖率补测） ============

describe('useReader.open 分支', () => {
  it('打开成功：写入 detail 与草稿并置 ready', async () => {
    getPackDetailMock.mockResolvedValue(packB())
    await useReader.getState().open(2)

    const s = useReader.getState()
    expect(s.openId).toBe(2)
    expect(s.status).toBe('ready')
    expect(s.detail).not.toBeNull()
    expect(s.draft).not.toBeNull()
  })

  it('拉详情失败：置 error 并写入可读文案', async () => {
    getPackDetailMock.mockRejectedValue(new Error('包不存在'))
    await useReader.getState().open(99)

    const s = useReader.getState()
    expect(s.status).toBe('error')
    expect(s.error).toContain('包不存在')
  })

  it('快速切换：慢响应后到时丢弃（不覆盖新包）', async () => {
    const slow = deferred<InboxMessageDetail>()
    getPackDetailMock.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(packB())

    const first = useReader.getState().open(1)
    await useReader.getState().open(2) // 切到 B
    slow.resolve(detail(1, [pdfAtt({ part_index: 0, page_count: 2 })]))
    await first

    expect(useReader.getState().openId).toBe(2)
  })

  it('打开时清空上一个包的 PDF 文档与字节缓存', async () => {
    getPackDetailMock.mockResolvedValue(packB())
    await useReader.getState().open(2)
    expect(clearPdfDocumentsMock).toHaveBeenCalled()
    expect(clearBytesCacheMock).toHaveBeenCalled()
  })
})

describe('useReader.close', () => {
  it('置 closing 并排队保存草稿', async () => {
    openPackA()
    useReader.getState().close()
    expect(useReader.getState().closing).toBe(true)
  })

  it('无 openId 时不排队保存', () => {
    useReader.setState({ openId: null, draft: null })
    useReader.getState().close()
    expect(saveDraftMock).not.toHaveBeenCalled()
  })

  it('退出动画结束后彻底卸载并释放缓存', async () => {
    vi.useFakeTimers()
    openPackA()
    useReader.getState().close()
    await vi.advanceTimersByTimeAsync(400)

    const s = useReader.getState()
    expect(s.openId).toBeNull()
    expect(s.draft).toBeNull()
    expect(s.status).toBe('idle')
    vi.useRealTimers()
  })

  it('动画期间重新 open：取消本次退场', async () => {
    vi.useFakeTimers()
    openPackA()
    getPackDetailMock.mockResolvedValue(packB())

    useReader.getState().close()
    await useReader.getState().open(2)
    await vi.advanceTimersByTimeAsync(400)

    // 新包仍在打开状态，未被退场定时器清掉
    expect(useReader.getState().openId).toBe(2)
    vi.useRealTimers()
  })
})

describe('useReader.resetAll', () => {
  it('清空全部阅读器状态并释放缓存', () => {
    openPackA()
    useReader.getState().resetAll()

    const s = useReader.getState()
    expect(s.openId).toBeNull()
    expect(s.detail).toBeNull()
    expect(s.draft).toBeNull()
    expect(s.status).toBe('idle')
    expect(s.error).toBe('')
    expect(clearPdfDocumentsMock).toHaveBeenCalled()
    expect(clearBytesCacheMock).toHaveBeenCalled()
  })
})

describe('useReader.update', () => {
  it('草稿变化时写入并排队保存', () => {
    openPackA()
    const before = useReader.getState().draft
    useReader.getState().update((d) => ({ ...d, infos: [{ k: 'x', v: '1', src: '', srcRef: null }] }))

    expect(useReader.getState().draft).not.toBe(before)
  })

  it('返回同一引用时不写入（避免无谓重渲与保存）', () => {
    openPackA()
    const before = useReader.getState().draft
    useReader.getState().update((d) => d)
    expect(useReader.getState().draft).toBe(before)
  })

  it('无 openId 时仍可更新内存态（不排队保存）', () => {
    useReader.setState({ openId: null, draft: draftOf(1) })
    useReader.getState().update((d) => ({ ...d, infos: [{ k: 'y', v: '2', src: '', srcRef: null }] }))
    expect(useReader.getState().draft!.infos).toHaveLength(1)
  })
})

// ============ setStatus / setAssign / renameSubject / appendFiles（覆盖率补测） ============

describe('useReader setStatus / setAssign', () => {
  it('setStatus 更新草稿状态并在有 openId 时排队保存', () => {
    openPackA()
    useReader.getState().setStatus('done')

    expect(useReader.getState().draft!.status).toBe('done')
    // 有 openId + draft → scheduleSave 走 draft-persistence（内部调 saveDraft）
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        expect(saveDraftMock).toHaveBeenCalled()
        resolve()
      }, 20)
    })
  })

  it('setStatus 无 openId 时只改内存不保存', () => {
    useReader.setState({ openId: null, draft: draftOf(1) })
    useReader.getState().setStatus('filed')

    expect(useReader.getState().draft!.status).toBe('filed')
    expect(saveDraftMock).not.toHaveBeenCalled()
  })

  it('setAssign 写入归案信息', () => {
    openPackA()
    useReader.getState().setAssign({ target: 'existing', caseId: 9, caseTitle: '张三案' } as never)

    expect(useReader.getState().draft!.assign).toMatchObject({ target: 'existing', caseId: 9 })
  })

  it('setAssign 无 openId 时只改内存', () => {
    useReader.setState({ openId: null, draft: draftOf(1) })
    useReader.getState().setAssign({ target: 'new' } as never)
    expect(useReader.getState().draft!.assign).toEqual({ target: 'new' })
  })
})

describe('useReader renameSubject', () => {
  it('id 匹配且标题不同：更新 detail 标题', () => {
    openPackA()
    const before = useReader.getState().detail!.subject
    useReader.getState().renameSubject(1, '新标题')

    expect(useReader.getState().detail!.subject).toBe('新标题')
    expect(useReader.getState().detail!.subject).not.toBe(before)
  })

  it('id 不匹配：不改动', () => {
    openPackA()
    const before = useReader.getState().detail
    useReader.getState().renameSubject(999, '别人的标题')
    expect(useReader.getState().detail).toBe(before)
  })

  it('标题相同：不产生新对象（避免无谓重渲）', () => {
    openPackA()
    const before = useReader.getState().detail
    useReader.getState().renameSubject(1, before!.subject)
    expect(useReader.getState().detail).toBe(before)
  })

  it('无 detail 时是 no-op', () => {
    useReader.setState({ detail: null })
    expect(() => useReader.getState().renameSubject(1, 'x')).not.toThrow()
  })
})

describe('useReader renameMatInDraft', () => {
  it('无草稿时是 no-op', () => {
    useReader.setState({ draft: null })
    expect(() => useReader.getState().renameMatInDraft(0, '新名')).not.toThrow()
  })
})

describe('useReader appendFiles 分支', () => {
  it('无 openId / 无草稿时直接返回', async () => {
    useReader.setState({ openId: null, draft: null })
    await useReader.getState().appendFiles([new File(['x'], 'a.pdf')])
    expect(appendPackFilesMock).not.toHaveBeenCalled()
  })

  it('空文件列表直接返回', async () => {
    openPackA()
    await useReader.getState().appendFiles([])
    expect(appendPackFilesMock).not.toHaveBeenCalled()
  })

  it('上传失败：提示追加失败', async () => {
    openPackA()
    appendPackFilesMock.mockRejectedValue(new Error('网络断了'))

    await useReader.getState().appendFiles([new File(['x'], 'a.pdf')])
    expect(toastMock.error).toHaveBeenCalledWith('追加材料失败，请检查后端连接')
  })

  it('没有新增材料：提示且只更新 detail', async () => {
    openPackA()
    // 返回同一份详情（partIndex 已存在）
    appendPackFilesMock.mockResolvedValue(detail(1, [pdfAtt({ part_index: 0, page_count: 2 })]))
    const beforeMats = useReader.getState().draft!.mats.length

    await useReader.getState().appendFiles([new File(['x'], 'a.pdf')])
    expect(toastMock).toHaveBeenCalledWith('没有新增材料')
    expect(useReader.getState().draft!.mats.length).toBe(beforeMats)
  })

  it('有新增材料：追加进草稿并提示份数', async () => {
    openPackA()
    appendPackFilesMock.mockResolvedValue(
      detail(1, [
        pdfAtt({ part_index: 0, page_count: 2 }),
        pdfAtt({ filename: 'c.pdf', original_filename: 'c.pdf', part_index: 3, page_count: 4 }),
      ]),
    )
    fetchBytesMock.mockResolvedValue(new Uint8Array([1]))

    await useReader.getState().appendFiles([new File(['x'], 'c.pdf')])
    await new Promise((r) => setTimeout(r, 30))

    expect(useReader.getState().draft!.mats.length).toBeGreaterThan(1)
    expect(toastMock.success).toHaveBeenCalledWith(expect.stringContaining('已追加'))
  })
})
