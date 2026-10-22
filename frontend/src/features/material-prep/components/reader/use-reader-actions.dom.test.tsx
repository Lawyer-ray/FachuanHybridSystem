// @vitest-environment jsdom
/**
 * useReaderActions 测试（jsdom）。
 *
 * 覆盖：换包重置聚焦段、缩放上下限、重置分段（含无草稿兜底）、
 * 归档留痕、删页二次确认（未选目标时不删）。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  openId: 1 as number | null,
  zoom: 1,
  setZoom: vi.fn(),
  update: vi.fn(),
  setStatus: vi.fn(),
  close: vi.fn(),
  deleteSelected: vi.fn(() => 2),
}))
const draftMock = vi.hoisted(() => ({ resetSegments: vi.fn((d: unknown) => d) }))

vi.mock('sonner', () => ({ toast: vi.fn() }))
vi.mock('../../store', () => ({
  useReader: Object.assign(
    (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
    { getState: () => storeMock },
  ),
}))
vi.mock('../../draft', () => draftMock)
vi.mock('./ui', () => ({ ZOOM_MIN: 0.5, ZOOM_MAX: 2.5, ZOOM_STEP: 0.1 }))

import { toast } from 'sonner'

import { useReaderActions } from './use-reader-actions'

const DRAFT = { mats: [], segs: [], infos: [] } as never

beforeEach(() => {
  vi.clearAllMocks()
  storeMock.openId = 1
  storeMock.zoom = 1
  storeMock.setZoom = vi.fn()
  storeMock.update = vi.fn()
  storeMock.setStatus = vi.fn()
  storeMock.close = vi.fn()
  storeMock.deleteSelected = vi.fn(() => 2)
})

describe('useReaderActions：聚焦段', () => {
  it('初始聚焦第 0 段', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    expect(result.current.focusedSeg).toBe(0)
  })

  it('focusSeg 更新聚焦并平滑滚动到对应元素', () => {
    const target = document.createElement('div')
    target.id = 'seg-2'
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)

    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.focusSeg(2)
    })
    expect(result.current.focusedSeg).toBe(2)

    // requestAnimationFrame 在 jsdom 下需要手动推进
    return new Promise<void>((resolve) => {
      requestAnimationFrame(() => {
        expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
        target.remove()
        resolve()
      })
    })
  })

  it('换包（openId 变化）时聚焦段重置为 0', () => {
    const { result, rerender } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.focusSeg(3)
    })
    expect(result.current.focusedSeg).toBe(3)

    storeMock.openId = 2
    rerender()
    expect(result.current.focusedSeg).toBe(0)
  })
})

describe('useReaderActions：缩放', () => {
  it('zoomIn 按步长增加并四舍五入到两位', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.zoomIn()
    })
    expect(storeMock.setZoom).toHaveBeenCalledWith(1.1)
  })

  it('zoomOut 按步长减少', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.zoomOut()
    })
    expect(storeMock.setZoom).toHaveBeenCalledWith(0.9)
  })

  it('zoomIn 不超过上限', () => {
    storeMock.zoom = 2.5
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.zoomIn()
    })
    expect(storeMock.setZoom).toHaveBeenCalledWith(2.5)
  })

  it('zoomOut 不低于下限', () => {
    storeMock.zoom = 0.5
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.zoomOut()
    })
    expect(storeMock.setZoom).toHaveBeenCalledWith(0.5)
  })
})

describe('useReaderActions：重置分段', () => {
  it('有草稿时调用 update 并提示', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.onResetSegments()
    })
    expect(storeMock.update).toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith('已恢复初始分段')
  })

  it('无草稿时不做任何事', () => {
    const { result } = renderHook(() => useReaderActions(null))
    act(() => {
      result.current.onResetSegments()
    })
    expect(storeMock.update).not.toHaveBeenCalled()
  })
})

describe('useReaderActions：归档留痕', () => {
  it('onReject 置 filed 状态、提示并关闭阅读器', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.onReject()
    })
    expect(storeMock.setStatus).toHaveBeenCalledWith('filed')
    expect(toast).toHaveBeenCalledWith('已归档留痕，未建案')
    expect(storeMock.close).toHaveBeenCalled()
  })
})

describe('useReaderActions：删页二次确认', () => {
  it('有目标时删除并提示页数，随后清空目标', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))

    act(() => {
      result.current.setDeleteTarget([{ mi: 0, p: 1 }, { mi: 0, p: 2 }])
    })
    act(() => {
      result.current.confirmDelete()
    })

    expect(storeMock.deleteSelected).toHaveBeenCalledWith([
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
    ])
    expect(toast).toHaveBeenCalledWith('已删除 2 页')
    expect(result.current.deleteTarget).toBeNull()
  })

  it('无目标时确认不删除（只是关掉确认框）', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.confirmDelete()
    })
    expect(storeMock.deleteSelected).not.toHaveBeenCalled()
    expect(result.current.deleteTarget).toBeNull()
  })

  it('空数组目标同样不删除', () => {
    const { result } = renderHook(() => useReaderActions(DRAFT))
    act(() => {
      result.current.setDeleteTarget([])
    })
    act(() => {
      result.current.confirmDelete()
    })
    expect(storeMock.deleteSelected).not.toHaveBeenCalled()
  })
})
