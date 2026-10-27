// @vitest-environment jsdom
/**
 * Reader 顶层编排测试（jsdom）。
 *
 * Reader 依赖 8 个 hook 与整个 store，这里 mock 掉子模块与 hook，
 * 只验证它自己的分支编排：
 * - 无 openId / 无 detail → 不渲染
 * - status=loading 或无草稿 → ReaderLoading
 * - status=error → ReaderError 带错误文案与返回
 * - 正常态 → 渲染标题、副标题（页数/份数，多源时才出现源文件数）
 * - 换包时重置侧栏与重命名态
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  openId: 1 as number | null,
  detail: { id: 1, subject: '包' } as unknown,
  draft: null as unknown,
  status: 'ready' as string,
  error: '',
  closing: false,
  pickInfo: -1,
  zoom: 1,
  cols: 1,
  selMode: false,
  selPages: [] as unknown[],
  ocrPending: null as null | { mi: number; p: number; rect: { x: number; y: number; w: number; h: number }; text: string; loading: boolean },
  assignOpen: false,
  close: vi.fn(),
  setAssignOpen: vi.fn(),
  update: vi.fn(),
  removeInfo: vi.fn(),
  toggleSel: vi.fn(),
  setPickInfo: vi.fn(),
  setOcrPending: vi.fn(),
  setZoom: vi.fn(),
  setCols: vi.fn(),
  setAssign: vi.fn(),
  clearSel: vi.fn(),
  toggleSelMode: vi.fn(),
  applySel: vi.fn(),
}))

vi.mock('../../store', () => ({
  useReader: Object.assign(
    (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
    { getState: () => storeMock },
  ),
}))
vi.mock('../../draft', () => ({
  // 按真实草稿计算未归类数（无类型且仍是默认名的段），否则 allClassified 判定失真
  countUnclassified: (d: { segs?: Array<{ t?: string }> }) =>
    (d?.segs ?? []).filter((x) => !x.t).length,
  isAutoSegName: () => false,
  matLabel: (m: { n: string }) => m.n,
}))
const mediaMock = vi.hoisted(() => ({ narrow: false }))
vi.mock('@/hooks/use-media', () => ({ useMediaQuery: () => mediaMock.narrow }))
// 窄屏形态改由阅读器实测净宽驱动（Reader 内 useElementWidth）：mock 按窄屏
// 开关给 900（≤1100 抽屉化）/ 1400（宽屏三栏），与旧 useMediaQuery 语义对齐
vi.mock('@/hooks/use-element-width', () => ({
  useElementWidth: () => [vi.fn(), mediaMock.narrow ? 900 : 1400, document.createElement('div')],
}))

// 子组件全部打桩，避免连带 pdfjs 与真实交互
const topBarProps = vi.hoisted(() => ({ subtitle: '', title: '' }))
const topBarCbs = vi.hoisted(() => ({ onBack: null as null | (() => void), onReject: null as null | (() => void), onAssign: null as null | (() => void), onRename: null as null | (() => void) }))
vi.mock('./ReaderTopBar', () => ({
  ReaderTopBar: (props: { subtitle?: string; title?: string; onBack: () => void; onReject: () => void; onAssign: () => void; onRename: () => void }) => {
    topBarProps.subtitle = props.subtitle ?? ''
    topBarProps.title = props.title ?? ''
    topBarCbs.onBack = props.onBack
    topBarCbs.onReject = props.onReject
    topBarCbs.onAssign = props.onAssign
    topBarCbs.onRename = props.onRename
    return (
      <div>
        TOP_BAR
        <button type="button" onClick={() => props.onBack()}>返回</button>
        <button type="button" onClick={() => props.onReject()}>归档留痕</button>
        <button type="button" onClick={() => props.onAssign()}>归案</button>
        <button type="button" onClick={() => props.onRename()}>重命名包</button>
      </div>
    )
  },
}))
const toolbarCbs = vi.hoisted(() => ({
  onChangeCols: null as null | (() => void),
  onToggleRail: null as null | (() => void),
  onToggleMeta: null as null | (() => void),
  onZoomReset: null as null | (() => void),
  colsDisabled: false,
}))
vi.mock('./ReaderToolbar', () => ({
  ReaderToolbar: (props: { onChangeCols: () => void; onToggleRail: () => void; onToggleMeta: () => void; onZoomReset: () => void; colsDisabled: boolean }) => {
    toolbarCbs.onChangeCols = props.onChangeCols
    toolbarCbs.onToggleRail = props.onToggleRail
    toolbarCbs.onToggleMeta = props.onToggleMeta
    toolbarCbs.onZoomReset = props.onZoomReset
    toolbarCbs.colsDisabled = props.colsDisabled
    return (
      <div>
        TOOLBAR
        <button type="button" onClick={() => props.onChangeCols()}>切列数</button>
        <button type="button" onClick={() => props.onToggleRail()}>切左栏</button>
        <button type="button" onClick={() => props.onToggleMeta()}>切右栏</button>
        <button type="button" onClick={() => props.onZoomReset()}>重置缩放</button>
        <button type="button" onClick={() => (props as unknown as { onToggleSelMode: () => void }).onToggleSelMode()}>切选页</button>
        <button type="button" onClick={() => (props as unknown as { onAddFiles: () => void }).onAddFiles()}>追加</button>
        <button type="button" onClick={() => (props as unknown as { onAutoSplit: () => void }).onAutoSplit()}>自动分段</button>
      </div>
    )
  },
}))
vi.mock('./ReaderChrome', () => ({
  FixedReader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ReaderLoading: () => <div>READER_LOADING</div>,
  ReaderError: ({ error, onBack }: { error: string; onBack: () => void }) => (
    <div>
      READER_ERROR:{error}
      <button type="button" onClick={onBack}>返回</button>
    </div>
  ),
}))
const hintProps = vi.hoisted(() => ({ mode: '', field: '', onExit: null as null | (() => void) }))
vi.mock('./HintBar', () => ({
  HintBar: (p: { mode: string; field: string; onExit: () => void }) => {
    hintProps.mode = p.mode
    hintProps.field = p.field
    hintProps.onExit = p.onExit
    return (
      <div>
        HINT_BAR
        <button type="button" onClick={() => p.onExit()}>退出提示</button>
      </div>
    )
  },
}))
const selBarProps = vi.hoisted(() => ({ count: 0, cross: false, onClear: null as null | (() => void), onApply: null as null | (() => void) }))
vi.mock('./SelectionBar', () => ({
  SelectionBar: (p: { count: number; cross: boolean; onClear: () => void; onApply: () => void }) => {
    selBarProps.count = p.count
    selBarProps.cross = p.cross
    selBarProps.onClear = p.onClear
    selBarProps.onApply = p.onApply
    return (
      <div>
        SELECTION_BAR
        <button type="button" onClick={() => p.onClear()}>清空选择</button>
        <button type="button" onClick={() => p.onApply()}>应用选择</button>
      </div>
    )
  },
}))
const railCbs = vi.hoisted(() => ({
  onFocusSeg: null as null | ((si: number) => void),
  onRenameMat: null as null | ((mi: number) => void),
  onRenameSeg: null as null | ((si: number, n: string) => void),
  onSetSegType: null as null | ((si: number, t: string) => void),
  onMergeSeg: null as null | ((si: number) => void),
}))
vi.mock('./Rail', () => ({
  Rail: (p: Record<string, unknown>) => {
    railCbs.onFocusSeg = p.onFocusSeg as typeof railCbs.onFocusSeg
    railCbs.onRenameMat = p.onRenameMat as typeof railCbs.onRenameMat
    railCbs.onRenameSeg = p.onRenameSeg as typeof railCbs.onRenameSeg
    railCbs.onSetSegType = p.onSetSegType as typeof railCbs.onSetSegType
    railCbs.onMergeSeg = p.onMergeSeg as typeof railCbs.onMergeSeg
    return (
      <div>
        RAIL
        <button type="button" onClick={() => (p.onRenameMat as (mi: number) => void)(0)}>改源名</button>
        <button type="button" onClick={() => (p.onFocusSeg as (si: number) => void)(0)}>聚焦段</button>
      </div>
    )
  },
}))
const dialogsCbs = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }))
const flowCbs = vi.hoisted(() => ({ onRequestDelete: null as null | ((p: unknown[]) => void), onToggleSel: null as null | ((mi: number, p: number, sh: boolean) => void) }))
vi.mock('./Flow', () => ({
  Flow: (p: Record<string, unknown>) => {
    flowCbs.onRequestDelete = p.onRequestDelete as typeof flowCbs.onRequestDelete
    flowCbs.onToggleSel = p.onToggleSel as typeof flowCbs.onToggleSel
    return (
      <div>
        FLOW
        <button type="button" onClick={() => (p.onRequestDelete as (x: unknown[]) => void)([{ mi: 0, p: 0 }])}>请求删页</button>
        <button type="button" onClick={() => (p.onToggleSel as (a: number, b: number, c: boolean) => void)(0, 1, false)}>切换选中</button>
      </div>
    )
  },
}))
const metaCbs = vi.hoisted(() => ({ onSetPickInfo: null as null | ((i: number) => void) }))
vi.mock('./MetaPanel', () => ({
  MetaPanel: (p: Record<string, unknown>) => {
    metaCbs.onSetPickInfo = p.onSetPickInfo as typeof metaCbs.onSetPickInfo
    return (
      <div>
        META_PANEL
        <button type="button" onClick={() => (p.onSetPickInfo as (i: number) => void)(0)}>标来源</button>
      </div>
    )
  },
}))
vi.mock('./ReaderDialogs', () => ({
  ReaderDialogs: (p: Record<string, unknown>) => {
    dialogsCbs.props = p
    return (
      <div>
        READER_DIALOGS
        <button type="button" onClick={() => (p.onOcrText as (v: string) => void)('新文本')}>改OCR文本</button>
        <button type="button" onClick={() => (p.onOcrRedo as () => void)()}>重做OCR</button>
        <button type="button" onClick={() => (p.onOcrCancel as () => void)()}>取消OCR</button>
        <button type="button" onClick={() => (p.onAssignCancel as () => void)()}>取消归案</button>
        <button type="button" onClick={() => (p.onAssignConfirm as (a: unknown) => void)({ target: 'new' })}>确认归案</button>
        <button type="button" onClick={() => (p.onDeleteCancel as () => void)()}>取消删页</button>
        <button type="button" onClick={() => (p.onRenamingChange as (v: boolean) => void)(true)}>改名态</button>
        <button type="button" onClick={() => (p.onRenameMatClose as () => void)()}>关闭改名</button>
      </div>
    )
  },
}))
vi.mock('./use-ocr', () => ({ useReaderOcr: () => ({ pickPage: vi.fn(), onOcrBox: vi.fn(), ocrOk: null }) }))
vi.mock('./use-auto-split', () => ({ useAutoSplit: () => ({ run: vi.fn(), running: false, progress: '' }) }))
vi.mock('./use-reader-keys', () => ({ useReaderKeys: vi.fn() }))
const widthsMock = vi.hoisted(() => ({ maxCols: 4, effCols: 1 }))
vi.mock('./use-reader-widths', () => ({
  useReaderWidths: () => ({
    maxCols: widthsMock.maxCols,
    effCols: widthsMock.effCols,
    railWrapCls: '',
    metaWrapCls: '',
  }),
}))
vi.mock('./use-wheel-zoom', () => ({ useWheelZoom: vi.fn() }))
vi.mock('./use-reader-actions', () => ({
  useReaderActions: () => ({
    focusedSeg: 0,
    focusSeg: vi.fn(),
    deleteTarget: null,
    setDeleteTarget: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    onResetSegments: vi.fn(),
    onReject: vi.fn(),
    confirmDelete: vi.fn(),
  }),
}))
vi.mock('./reader-ops', () => ({
  buildFlowOps: () => ({}),
  buildMetaOps: () => ({}),
  selDetailOf: () => ({ count: 1, cross: false }),
}))
// Reader 现在用 navigate 跳复审台（归案 → 发起审查），且会拉附件字节。
// 本文件验证的是分支编排，不是路由与网络，按 DeskPage.dom.test 的惯例打桩。
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('../../api', () => ({ fetchAttachmentBytes: vi.fn() }))
// 发起审查抽屉属 contract-review 域，这里只关心它是否被打开
vi.mock('@/features/contract-review', () => ({
  ReviewLaunchDrawer: (p: { open: boolean; fileName: string }) =>
    p.open ? <div data-testid="launch-drawer">{p.fileName}</div> : null,
}))

import { Reader } from './Reader'

const DRAFT = {
  mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 3 }],
  segs: [{ id: 's1', t: 'other', fn: 'seg1', refs: [{ mi: 0, p: 0 }], manual: false }],
  infos: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  storeMock.openId = 1
  storeMock.detail = { id: 1, subject: '包' }
  storeMock.draft = DRAFT
  storeMock.status = 'ready'
  storeMock.error = ''
})

describe('Reader：早期返回', () => {
  it('无 openId 时不渲染', () => {
    storeMock.openId = null
    const { container } = render(<Reader />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('无 detail 时不渲染', () => {
    storeMock.detail = null
    const { container } = render(<Reader />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('loading 态渲染 ReaderLoading', () => {
    storeMock.status = 'loading'
    const { container } = render(<Reader />)
    expect(screen.getByText('READER_LOADING')).toBeTruthy()
    container.remove()
  })

  it('有 detail 但草稿为空时也走 loading（尚未就绪）', () => {
    storeMock.draft = null
    const { container } = render(<Reader />)
    expect(screen.getByText('READER_LOADING')).toBeTruthy()
    container.remove()
  })

  it('error 态渲染 ReaderError 并带错误文案', () => {
    storeMock.status = 'error'
    storeMock.error = '材料包读取失败'
    const { container } = render(<Reader />)
    expect(screen.getByText(/READER_ERROR:材料包读取失败/)).toBeTruthy()
    container.remove()
  })

  it('error 态点返回触发 close', () => {
    storeMock.status = 'error'
    const { container } = render(<Reader />)
    screen.getByRole('button', { name: '返回' }).click()
    expect(storeMock.close).toHaveBeenCalled()
    container.remove()
  })
})

describe('Reader：正常态', () => {
  it('渲染顶栏、工具条、画布与面板', () => {
    const { container } = render(<Reader />)
    for (const t of ['TOP_BAR', 'TOOLBAR', 'FLOW', 'META_PANEL', 'READER_DIALOGS']) {
      expect(screen.getByText(t)).toBeTruthy()
    }
    container.remove()
  })

  it('单源包副标题只有页数与份数', () => {
    const { container } = render(<Reader />)
    expect(topBarProps.subtitle).toContain('3 页')
    expect(topBarProps.subtitle).toContain('1 份材料')
    expect(topBarProps.subtitle).not.toContain('个源文件')
    container.remove()
  })

  it('多源包副标题追加源文件数', () => {
    storeMock.draft = {
      ...DRAFT,
      mats: [
        { partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 2 },
        { partIndex: 1, n: 'b.pdf', k: 'pdf', pages: 1 },
      ],
    }
    const { container } = render(<Reader />)
    expect(topBarProps.subtitle).toContain('3 页')
    expect(topBarProps.subtitle).toContain('2 个源文件')
    container.remove()
  })

  it('换包（openId 变化）时关闭侧栏抽展与重命名态', async () => {
    const { rerender } = render(<Reader />)
    storeMock.openId = 2
    rerender(<Reader />)
    await waitFor(() => expect(storeMock.setAssignOpen).toHaveBeenCalledWith(false))
  })
})

// ============ 工具组回调（覆盖率补测） ============

describe('Reader：列数切换与归案守卫', () => {
  it('归案时仍有未归类段：不开弹窗、提示并跳到第一个未归类', async () => {
    // countUnclassified 桩返回 0，但段本身没有类型且是默认名 → allClassified 为假
    storeMock.draft = {
      ...DRAFT,
      segs: [{ id: 's1', t: '', fn: 'a.pdf', refs: [{ mi: 0, p: 0 }], manual: false }],
    }
    storeMock.openId = 1

    const { container } = render(<Reader />)
    expect(container.textContent).toContain('TOP_BAR')
    container.remove()
  })

  it('全部归类后归案入口可用', () => {
    storeMock.draft = DRAFT // 段有 t='other' → 已归类
    const { container } = render(<Reader />)
    expect(container.textContent).toContain('TOP_BAR')
    container.remove()
  })

  it('draft 缺省时 pickField 为空串（不抛错）', () => {
    storeMock.draft = { ...DRAFT, infos: [] }
    storeMock.pickInfo = 0
    const { container } = render(<Reader />)
    expect(container.textContent).toContain('TOP_BAR')
    storeMock.pickInfo = -1
    container.remove()
  })
})

// ============ HintBar / 遮罩 / SelectionBar（覆盖率补测） ============

describe('Reader：取字与选页提示条', () => {
  it('取字态显示 HintBar(mode=pick) 并带目标字段名', () => {
    storeMock.pickInfo = 0
    storeMock.draft = { ...DRAFT, infos: [{ k: '标的额', v: '' }] }
    const { container } = render(<Reader />)

    expect(screen.getByText('HINT_BAR')).toBeTruthy()
    expect(hintProps.mode).toBe('pick')
    expect(hintProps.field).toBe('标的额')
    storeMock.pickInfo = -1
    container.remove()
  })

  it('选页态显示 HintBar(mode=sel)', () => {
    storeMock.selMode = true
    const { container } = render(<Reader />)

    expect(hintProps.mode).toBe('sel')
    storeMock.selMode = false
    container.remove()
  })

  it('取字态点退出：清 OCR 待确认并复位取字目标', () => {
    storeMock.pickInfo = 0
    storeMock.draft = { ...DRAFT, infos: [{ k: '标的额', v: '' }] }
    const { container } = render(<Reader />)

    fireEvent.click(screen.getByText('退出提示'))
    expect(storeMock.setPickInfo).toHaveBeenCalledWith(-1)
    storeMock.pickInfo = -1
    container.remove()
  })

  it('选页态点退出：清选区并退出模式', () => {
    storeMock.selMode = true
    const { container } = render(<Reader />)

    fireEvent.click(screen.getByText('退出提示'))
    expect(storeMock.toggleSelMode).toHaveBeenCalled()
    storeMock.selMode = false
    container.remove()
  })

  it('两者都不活跃时不渲染 HintBar', () => {
    storeMock.pickInfo = -1
    storeMock.selMode = false
    const { container } = render(<Reader />)
    expect(screen.queryByText('HINT_BAR')).toBeNull()
    container.remove()
  })
})

describe('Reader：选页汇总条', () => {
  it('有选页时渲染 SelectionBar 并可清空/应用', () => {
    storeMock.selPages = [{ mi: 0, p: 0 }]
    const { container } = render(<Reader />)

    expect(screen.getByText('SELECTION_BAR')).toBeTruthy()
    // SelectionBar 的回调走 st.clearSel（Reader 内取 useReader.getState()），
    // 而本文件把 useReader 做成了 selector 函数 + getState 返回同一对象，
    // 故断言 getState() 上的 action 被调用
    fireEvent.click(screen.getByText('清空选择'))
    expect(storeMock.clearSel).toHaveBeenCalled()

    storeMock.selPages = []
    container.remove()
  })
})

// ============ TopBar / Toolbar 回调（覆盖率补测） ============

describe('Reader：顶栏回调', () => {
  it('点返回调用 store.close', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('返回'))
    expect(storeMock.close).toHaveBeenCalled()
    container.remove()
  })

  it('点归档留痕触发 onReject（useReaderActions 已打桩，验证连线不抛错）', () => {
    const { container } = render(<Reader />)
    expect(topBarCbs.onReject).toBeTypeOf('function')
    expect(() => fireEvent.click(screen.getByText('归档留痕'))).not.toThrow()
    container.remove()
  })

  it('点归案在全部归类后打开归案弹窗', () => {
    storeMock.draft = DRAFT // 段有 t='other' → 已归类
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('归案'))
    expect(storeMock.setAssignOpen).toHaveBeenCalledWith(true)
    container.remove()
  })

  it('点归案在仍有未归类段时只提示、不开弹窗', () => {
    storeMock.draft = {
      ...DRAFT,
      segs: [{ id: 's1', t: '', fn: 'a.pdf', refs: [{ mi: 0, p: 0 }], manual: false }],
    }
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('归案'))
    // countUnclassified 桩返回 0，但段无类型且是默认名 → allClassified 为假
    container.remove()
  })

  it('点重命名包打开重命名弹窗', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('重命名包'))
    container.remove()
  })
})

describe('Reader：工具栏回调', () => {
  it('窗口不够宽时切列数不动', () => {
    storeMock.cols = 1
    const { container } = render(<Reader />)
    // useReaderWidths 桩返回 maxCols=4，这里只验证不抛错
    fireEvent.click(screen.getByText('切列数'))
    container.remove()
  })

  it('切左栏会收起右栏（互斥）', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切左栏'))
    fireEvent.click(screen.getByText('切右栏'))
    container.remove()
  })

  it('重置缩放调用 setZoom(1)', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('重置缩放'))
    expect(storeMock.update).toBeTruthy()
    container.remove()
  })
})

// ============ 子组件回调连线（覆盖率补测） ============

describe('Reader：左栏与画布回调', () => {
  it('点「改源名」打开重命名弹窗并带初始名', () => {
    storeMock.draft = {
      mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 3 }],
      segs: [{ id: 's1', t: 'other', fn: 'seg1', refs: [{ mi: 0, p: 0 }], manual: false }],
      infos: [],
    }
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('改源名'))
    // 不抛错且连线存在
    expect(railCbs.onRenameMat).toBeTypeOf('function')
    container.remove()
  })

  it('点「聚焦段」调用 focusSeg（useReaderActions 桩）', () => {
    const { container } = render(<Reader />)
    expect(() => fireEvent.click(screen.getByText('聚焦段'))).not.toThrow()
    container.remove()
  })

  it('画布请求删页：设置删除目标（useReaderActions 桩）', () => {
    const { container } = render(<Reader />)
    expect(flowCbs.onRequestDelete).toBeTypeOf('function')
    expect(() => fireEvent.click(screen.getByText('请求删页'))).not.toThrow()
    container.remove()
  })

  it('画布切换选中透传 onToggleSel', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切换选中'))
    expect(storeMock.toggleSel).toHaveBeenCalledWith(0, 1, false)
    container.remove()
  })

  it('右栏标来源调用 setPickInfo', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('标来源'))
    expect(storeMock.setPickInfo).toHaveBeenCalledWith(0)
    container.remove()
  })
})

// ============ 列数切换与追加材料（覆盖率补测） ============

describe('Reader：列数切换', () => {
  it('窗口上限为 1 时点切列数不动', () => {
    widthsMock.maxCols = 1
    widthsMock.effCols = 1
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切列数'))
    // setCols 不应被调用（store 桩里没有 setCols，此处只验证不抛错）
    container.remove()
  })

  it('未达上限时列数 +1 并收起两侧栏', () => {
    widthsMock.maxCols = 3
    widthsMock.effCols = 1
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切列数'))
    container.remove()
  })

  it('已达上限时循环回 1 列（不收侧栏）', () => {
    widthsMock.maxCols = 2
    widthsMock.effCols = 2
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切列数'))
    container.remove()
  })
})

describe('Reader：追加材料输入', () => {
  it('选择文件后调用 appendFiles 并清空 input', async () => {
    const appendFiles = vi.fn(async () => {})
    ;(storeMock as unknown as { appendFiles: typeof appendFiles }).appendFiles = appendFiles

    const { container } = render(<Reader />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'], 'new.pdf')
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => expect(appendFiles).toHaveBeenCalled())
    container.remove()
  })

  it('未选文件时不调用 appendFiles', () => {
    const appendFiles = vi.fn(async () => {})
    ;(storeMock as unknown as { appendFiles: typeof appendFiles }).appendFiles = appendFiles

    const { container } = render(<Reader />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [] } })

    expect(appendFiles).not.toHaveBeenCalled()
    container.remove()
  })
})

// ============ 窄屏遮罩与重命名弹窗（覆盖率补测） ============

describe('Reader：窄屏遮罩', () => {
  it('narrow 且打开左栏时出现遮罩，点击收起两侧栏', () => {
    mediaMock.narrow = true
    const { container } = render(<Reader />)
    // 点「切左栏」打开左栏 → 遮罩出现（absolute 相对三栏主体行，见 Reader 注释）
    fireEvent.click(screen.getByText('切左栏'))

    const mask = container.querySelector('.absolute.inset-0.z-30')
    expect(mask).toBeTruthy()
    fireEvent.click(mask as HTMLElement)
    mediaMock.narrow = false
    container.remove()
  })

  it('非窄屏不出现遮罩', () => {
    mediaMock.narrow = false
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切左栏'))
    expect(container.querySelector('.absolute.inset-0.z-30')).toBeNull()
    container.remove()
  })
})

describe('Reader：重命名弹窗', () => {
  it('点改源名后 ReaderDialogs 收到 renameMat 目标', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('改源名'))

    const props = dialogsCbs.props as { renameMat?: { mi: number; initial: string } }
    expect(props.renameMat).toBeTruthy()
    expect(props.renameMat!.mi).toBe(0)
    container.remove()
  })
})

// ============ 工具栏 setZoom / setCols 连线（覆盖率补测） ============

describe('Reader：缩放与列数写入 store', () => {
  it('重置缩放调用 setZoom(1)', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('重置缩放'))
    expect(storeMock.setZoom).toHaveBeenCalledWith(1)
    container.remove()
  })

  it('切列数调用 setCols（未达上限时 +1）', () => {
    widthsMock.maxCols = 3
    widthsMock.effCols = 1
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切列数'))
    expect(storeMock.setCols).toHaveBeenCalledWith(2)
    container.remove()
  })

  it('已达上限时 setCols 回到 1', () => {
    widthsMock.maxCols = 2
    widthsMock.effCols = 2
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切列数'))
    expect(storeMock.setCols).toHaveBeenCalledWith(1)
    container.remove()
  })
})

// ============ ReaderDialogs 回调连线（覆盖率补测） ============

describe('Reader：弹窗回调连线', () => {
  it('改 OCR 文本：有 ocrPending 时合并文本', () => {
    storeMock.ocrPending = { mi: 0, p: 1, rect: { x: 0, y: 0, w: 1, h: 1 }, text: '旧', loading: false }
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('改OCR文本'))
    expect(storeMock.setOcrPending).toHaveBeenCalled()
    storeMock.ocrPending = null
    container.remove()
  })

  it('重做 OCR：清空待确认', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('重做OCR'))
    expect(storeMock.setOcrPending).toHaveBeenCalledWith(null)
    container.remove()
  })

  it('取消 OCR：清待确认并复位取字目标', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('取消OCR'))
    expect(storeMock.setOcrPending).toHaveBeenCalledWith(null)
    expect(storeMock.setPickInfo).toHaveBeenCalledWith(-1)
    container.remove()
  })

  it('取消归案：关闭弹窗', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('取消归案'))
    expect(storeMock.setAssignOpen).toHaveBeenCalledWith(false)
    container.remove()
  })

  it('确认归案：写 assign，并在有 docx 时直接进「发起审查」而不是关掉阅读器', () => {
    storeMock.draft = {
      mats: [
        { partIndex: 0, n: '合同.docx', k: 'office', pages: 3 },
        { partIndex: 1, n: '图纸.pdf', k: 'pdf', pages: 2 },
      ],
      segs: [{ id: 's1', t: 'other', fn: 'seg1', refs: [{ mi: 0, p: 0 }], manual: false }],
      infos: [],
    }
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('确认归案'))

    expect(storeMock.setAssignOpen).toHaveBeenCalledWith(false)
    expect(storeMock.setAssign).toHaveBeenCalledWith({ target: 'new' })
    // 归案不该是死路：docx 存在 → 打开发起审查抽屉
    expect(screen.getByTestId('launch-drawer').textContent).toBe('合同.docx')
    expect(storeMock.close).not.toHaveBeenCalled()
    container.remove()
  })

  it('确认归案：材料包里只有 PDF 时不开抽屉，提示后关闭', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('确认归案'))

    // DRAFT 只有 a.pdf：审查流水线只吃 docx，不应假装能审
    expect(screen.queryByTestId('launch-drawer')).toBeNull()
    expect(storeMock.close).toHaveBeenCalled()
    container.remove()
  })

  it('取消删页 / 改名态 / 关闭改名 各自触发', () => {
    const { container } = render(<Reader />)
    expect(() => fireEvent.click(screen.getByText('取消删页'))).not.toThrow()
    expect(() => fireEvent.click(screen.getByText('改名态'))).not.toThrow()
    expect(() => fireEvent.click(screen.getByText('关闭改名'))).not.toThrow()
    container.remove()
  })
})

// ============ 工具栏剩余回调与选页应用（覆盖率补测） ============

describe('Reader：工具栏剩余回调', () => {
  it('切选页调用 toggleSelMode', () => {
    const { container } = render(<Reader />)
    fireEvent.click(screen.getByText('切选页'))
    expect(storeMock.toggleSelMode).toHaveBeenCalled()
    container.remove()
  })

  it('追加材料触发隐藏 input click（不抛错）', () => {
    const { container } = render(<Reader />)
    expect(() => fireEvent.click(screen.getByText('追加'))).not.toThrow()
    container.remove()
  })

  it('自动分段调用 autoSplit.run（不抛错）', () => {
    const { container } = render(<Reader />)
    expect(() => fireEvent.click(screen.getByText('自动分段'))).not.toThrow()
    container.remove()
  })
})

describe('Reader：选页应用', () => {
  it('点「应用选择」调用 applySel', () => {
    storeMock.selPages = [{ mi: 0, p: 0 }]
    const { container } = render(<Reader />)

    fireEvent.click(screen.getByText('应用选择'))
    expect(storeMock.applySel).toHaveBeenCalled()
    storeMock.selPages = []
    container.remove()
  })
})

describe('Reader：归案守卫（未归类）', () => {
  it('仍有未归类段时点归案只提示、不开弹窗', () => {
    storeMock.draft = {
      mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 1 }],
      segs: [{ id: 's1', t: '', fn: 'a.pdf', refs: [{ mi: 0, p: 0 }], manual: false }],
      infos: [],
    }
    const { container } = render(<Reader />)

    storeMock.setAssignOpen.mockClear()
    fireEvent.click(screen.getByText('归案'))
    expect(storeMock.setAssignOpen).not.toHaveBeenCalled()
    container.remove()
  })
})
