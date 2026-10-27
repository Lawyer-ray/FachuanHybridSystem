// @vitest-environment jsdom
/**
 * useReaderScreen 的接线测试（jsdom）。
 *
 * 这个 hook 与 Reader 一起把原来的单文件拆成了两层，这里守两条只有拆开才可能
 * 出错的契约（其余交互仍由 Reader.dom.test 覆盖）：
 *
 * 1. **补上 `clearOcrPick` 后不能漏接线**：OCR 面板的「取消」必须清掉待确认 OCR
 *    并复位取字目标（与 HintBar 退出、Esc 同一口径）。
 * 2. **store 读取一律走 selector**：旧实现混了一处 `useReader.getState()` 整份快照，
 *    靠 zustand action 引用恒定才侥幸成立。这里断言 hook 从不调 `getState()`。
 */
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  openId: 1 as number | null,
  detail: { id: 1, subject: '包' } as unknown,
  draft: {
    mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 3 }],
    segs: [{ id: 's1', t: 'other', fn: 'seg1', refs: [{ mi: 0, p: 0 }], manual: false }],
    infos: [],
  } as unknown,
  status: 'ready' as string,
  error: '',
  closing: false,
  pickInfo: 0,
  zoom: 1,
  cols: 1,
  selMode: false,
  selPages: [] as unknown[],
  ocrPending: { mi: 0, p: 1, rect: { x: 0, y: 0, w: 1, h: 1 }, text: '旧', loading: false } as unknown,
  assignOpen: false,
  // 动作：断言「被调用」即可，具体行为由 store 单测覆盖
  setPickInfo: vi.fn(),
  setOcrPending: vi.fn(),
  // 视图态 effect 在挂载时会用到的其余动作
  setAssignOpen: vi.fn(),
  setAssign: vi.fn(),
  setCols: vi.fn(),
  setZoom: vi.fn(),
  clearSel: vi.fn(),
  toggleSelMode: vi.fn(),
  applySel: vi.fn(),
  appendFiles: vi.fn(),
  toggleSel: vi.fn(),
  update: vi.fn(),
  removeInfo: vi.fn(),
  close: vi.fn(),
}))

const getStateSpy = vi.hoisted(() => vi.fn(() => storeMock))

vi.mock('../../store', () => ({
  useReader: Object.assign((sel: (s: typeof storeMock) => unknown) => sel(storeMock), {
    getState: getStateSpy,
  }),
}))
vi.mock('@/hooks/use-element-width', () => ({
  useElementWidth: () => [vi.fn(), 1400, document.createElement('div')],
}))
vi.mock('./use-ocr', () => ({
  useReaderOcr: () => ({ pickPage: vi.fn(), onOcrBox: vi.fn(), ocrOk: vi.fn() }),
}))
vi.mock('./use-auto-split', () => ({ useAutoSplit: () => ({ run: vi.fn(), running: false, progress: '' }) }))
vi.mock('./use-reader-keys', () => ({ useReaderKeys: vi.fn() }))
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
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

import { useReaderScreen } from './use-reader-screen'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  getStateSpy.mockClear()
})

describe('useReaderScreen：store 读取方式', () => {
  it('只走字段 selector，不取整份 store 快照', () => {
    renderHook(() => useReaderScreen())
    expect(getStateSpy).not.toHaveBeenCalled()
  })

  it('把 pickInfo 派生成取字目标字段（HintBar 与 OCR 面板共用）', () => {
    const { result } = renderHook(() => useReaderScreen())
    // draft.infos 为空时字段名退化成空串，不抛错
    expect(result.current.pickField).toBe('')
  })
})
