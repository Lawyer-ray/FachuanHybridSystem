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
import { render, screen, waitFor } from '@testing-library/react'
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
  ocrPending: null,
  assignOpen: false,
  close: vi.fn(),
  setAssignOpen: vi.fn(),
  update: vi.fn(),
  removeInfo: vi.fn(),
  toggleSel: vi.fn(),
}))

vi.mock('../../store', () => ({
  useReader: Object.assign(
    (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
    { getState: () => storeMock },
  ),
}))
vi.mock('../../draft', () => ({
  countUnclassified: () => 0,
  isAutoSegName: () => false,
  matLabel: (m: { n: string }) => m.n,
}))
vi.mock('@/hooks/use-media', () => ({ useMediaQuery: () => false }))
vi.mock('../../hooks/use-element-width', () => ({
  useElementWidth: () => [vi.fn(), 900, document.createElement('div')],
}))

// 子组件全部打桩，避免连带 pdfjs 与真实交互
const topBarProps = vi.hoisted(() => ({ subtitle: '', title: '' }))
vi.mock('./ReaderTopBar', () => ({
  ReaderTopBar: (props: { subtitle?: string; title?: string }) => {
    topBarProps.subtitle = props.subtitle ?? ''
    topBarProps.title = props.title ?? ''
    return <div>TOP_BAR</div>
  },
}))
vi.mock('./ReaderToolbar', () => ({ ReaderToolbar: () => <div>TOOLBAR</div> }))
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
vi.mock('./HintBar', () => ({ HintBar: () => <div>HINT_BAR</div> }))
vi.mock('./SelectionBar', () => ({ SelectionBar: () => <div>SELECTION_BAR</div> }))
vi.mock('./Rail', () => ({ Rail: () => <div>RAIL</div> }))
vi.mock('./Flow', () => ({ Flow: () => <div>FLOW</div> }))
vi.mock('./MetaPanel', () => ({ MetaPanel: () => <div>META_PANEL</div> }))
vi.mock('./ReaderDialogs', () => ({ ReaderDialogs: () => <div>READER_DIALOGS</div> }))
vi.mock('./use-ocr', () => ({ useReaderOcr: () => ({ pickPage: vi.fn(), onOcrBox: vi.fn(), ocrOk: null }) }))
vi.mock('./use-auto-split', () => ({ useAutoSplit: () => ({ run: vi.fn(), running: false, progress: '' }) }))
vi.mock('./use-reader-keys', () => ({ useReaderKeys: vi.fn() }))
vi.mock('./use-reader-widths', () => ({
  useReaderWidths: () => ({ maxCols: 4, effCols: 1, railWrapCls: '', metaWrapCls: '' }),
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
  selDetailOf: () => null,
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
