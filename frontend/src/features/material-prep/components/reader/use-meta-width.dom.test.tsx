// @vitest-environment jsdom
/**
 * 右栏拖拽宽度的持久化契约。
 *
 * 需求原话：「右边的侧边栏应该支持手动拖拽增加宽度，宽度记在 localStorage 里，
 * 下次保持同样宽度」。这里锁三件事：读写档、夹取上下界、拖拽期间不写盘。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  META_DEFAULT_WIDTH,
  META_MAX_WIDTH,
  META_MIN_WIDTH,
  META_WIDE_DEFAULT,
  readMetaWidth,
  useMetaWidth,
} from './use-meta-width'

const KEY = 'mp.meta.width'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('readMetaWidth', () => {
  it('无存档返回 null（调用方用默认值）', () => {
    expect(readMetaWidth()).toBeNull()
  })

  it('存档被夹取到上下界内', () => {
    localStorage.setItem(KEY, '9999')
    expect(readMetaWidth()).toBe(META_MAX_WIDTH)
    localStorage.setItem(KEY, '1')
    expect(readMetaWidth()).toBe(META_MIN_WIDTH)
  })

  it('存档非法时退回 null，不抛', () => {
    localStorage.setItem(KEY, 'abc')
    expect(readMetaWidth()).toBeNull()
  })
})

describe('useMetaWidth', () => {
  it('优先用存档宽度', () => {
    localStorage.setItem(KEY, '420')
    const { result } = renderHook(() => useMetaWidth(false))
    expect(result.current.width).toBe(420)
  })

  it('无存档时宽屏用默认宽、窄屏用抽屉默认宽', () => {
    expect(renderHook(() => useMetaWidth(false)).result.current.width).toBe(META_DEFAULT_WIDTH)
    expect(renderHook(() => useMetaWidth(true)).result.current.width).toBe(META_WIDE_DEFAULT)
  })

  it('拖拽期间只更新宽度，pointerup 才落盘', () => {
    localStorage.setItem(KEY, '300')
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    const { result } = renderHook(() => useMetaWidth(false))

    const make = (type: string, clientX: number) =>
      ({ type, clientX, preventDefault: () => {}, currentTarget: { setPointerCapture() {}, releasePointerCapture() {} } }) as never

    act(() => result.current.onPointerDown(make('pointerdown', 500)))
    act(() => result.current.onPointerMove(make('pointermove', 400))) // 往左拖 100 → 变宽 100

    expect(result.current.width).toBe(400)
    // 拖拽中不写盘（localStorage 同步阻塞，每帧写会拖慢渲染）
    expect(spy.mock.calls.filter(([k]) => k === KEY)).toHaveLength(0)

    act(() => result.current.endDrag(make('pointerup', 400)))
    expect(spy.mock.calls.filter(([k]) => k === KEY)).toHaveLength(1)
    expect(localStorage.getItem(KEY)).toBe('400')
  })

  it('拖过界时夹在上下界内', () => {
    const { result } = renderHook(() => useMetaWidth(false))
    const make = (clientX: number) =>
      ({ clientX, preventDefault: () => {}, currentTarget: { setPointerCapture() {}, releasePointerCapture() {} } }) as never

    act(() => result.current.onPointerDown(make(0)))
    act(() => result.current.onPointerMove(make(-9999)))
    expect(result.current.width).toBe(META_MAX_WIDTH)

    act(() => result.current.onPointerMove(make(9999)))
    expect(result.current.width).toBe(META_MIN_WIDTH)
  })
})
