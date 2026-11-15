// @vitest-environment jsdom
/**
 * 左栏（材料目录）拖拽宽度的持久化契约。
 *
 * 与右栏 `use-meta-width.dom.test.tsx` 是两套独立实现（拖拽方向相反、键与区间
 * 各自独立），所以这里的用例也要完整走一遍：读档、夹取、拖拽期间不写盘、
 * 落盘只在 pointerup 发生一次。三件事各有真实代价：
 * - 拖拽期间每帧写 localStorage 是同步阻塞 IO，几百次会把拖动拖慢；
 * - 不夹取会让律师把左栏拖成 0 宽（或挤没中栏），下次进来是个坏掉的界面；
 * - 隐私模式下 `setItem` 会抛，抛出去就等于「一点手柄就白屏」。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  RAIL_DEFAULT_WIDTH,
  RAIL_MAX_WIDTH,
  RAIL_MIN_WIDTH,
  RAIL_WIDE_DEFAULT,
  readRailWidth,
  useRailWidth,
} from './use-rail-width'

const KEY = 'mp.rail.width'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('readRailWidth', () => {
  it('没存过 → null（由调用方给默认值）', () => {
    expect(readRailWidth()).toBeNull()
  })

  it('存档超上限 → 被 clamp 回上限', () => {
    localStorage.setItem(KEY, String(RAIL_MAX_WIDTH + 500))
    expect(readRailWidth()).toBe(RAIL_MAX_WIDTH)
  })

  it('存档低于下限 → 被 clamp 回下限', () => {
    localStorage.setItem(KEY, '10')
    expect(readRailWidth()).toBe(RAIL_MIN_WIDTH)
  })

  it('非法值 → null，不抛', () => {
    localStorage.setItem(KEY, 'abc')
    expect(readRailWidth()).toBeNull()
  })

  it('localStorage 抛错也不抛（隐私模式）', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(readRailWidth()).toBeNull()
    spy.mockRestore()
  })
})

describe('useRailWidth：初始宽度', () => {
  it('优先用存档宽度（换材料包打开也保持原样）', () => {
    localStorage.setItem(KEY, '420')
    expect(renderHook(() => useRailWidth(false)).result.current.width).toBe(420)
  })

  it('无存档时窄屏用 RAIL_DEFAULT_WIDTH、宽屏用 RAIL_WIDE_DEFAULT', () => {
    expect(renderHook(() => useRailWidth(false)).result.current.width).toBe(RAIL_DEFAULT_WIDTH)
    expect(renderHook(() => useRailWidth(true)).result.current.width).toBe(RAIL_WIDE_DEFAULT)
  })
})

/** 最小 PointerEvent 替身：hook 只读 clientX 并调 capture/release */
function pointer(clientX: number) {
  return {
    clientX,
    pointerId: 1,
    preventDefault: () => {},
    currentTarget: { setPointerCapture() {}, releasePointerCapture() {} },
  } as never
}

describe('useRailWidth：拖拽', () => {
  it('左栏往右拖 → 变宽（与右栏方向相反，写错了拖起来就是反的）', () => {
    localStorage.setItem(KEY, '300')
    const { result } = renderHook(() => useRailWidth(false))

    act(() => result.current.onPointerDown(pointer(100)))
    act(() => result.current.onPointerMove(pointer(160)))
    expect(result.current.width).toBe(360)
  })

  it('拖拽期间只改宽度、不写盘；pointerup 才落盘一次', () => {
    localStorage.setItem(KEY, '300')
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    const { result } = renderHook(() => useRailWidth(false))

    act(() => result.current.onPointerDown(pointer(0)))
    act(() => result.current.onPointerMove(pointer(50)))
    act(() => result.current.onPointerMove(pointer(80)))
    // 每帧写 = 几百次同步 IO，拖动会明显发涩
    expect(spy.mock.calls.filter(([k]) => k === KEY)).toHaveLength(0)

    act(() => result.current.endDrag(pointer(80)))
    expect(spy.mock.calls.filter(([k]) => k === KEY)).toHaveLength(1)
    expect(localStorage.getItem(KEY)).toBe('380')
  })

  it('没按下过就 move / up 不改变宽度（防止页边误拖）', () => {
    const { result } = renderHook(() => useRailWidth(false))
    act(() => result.current.onPointerMove(pointer(400)))
    expect(result.current.width).toBe(RAIL_DEFAULT_WIDTH)
    // 未拖拽时 endDrag 也不该落盘
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    act(() => result.current.endDrag(pointer(400)))
    expect(spy).not.toHaveBeenCalled()
  })

  it('拖过界时夹在上下界内（不能把左栏拖成 0 宽，也不能挤没中栏）', () => {
    const { result } = renderHook(() => useRailWidth(false))
    act(() => result.current.onPointerDown(pointer(0)))
    act(() => result.current.onPointerMove(pointer(9999)))
    expect(result.current.width).toBe(RAIL_MAX_WIDTH)

    act(() => result.current.onPointerMove(pointer(-9999)))
    expect(result.current.width).toBe(RAIL_MIN_WIDTH)
  })

  it('落盘失败（配额满 / 隐私模式）不影响本次会话宽度', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    const { result } = renderHook(() => useRailWidth(false))
    act(() => result.current.onPointerDown(pointer(0)))
    act(() => result.current.onPointerMove(pointer(100)))
    expect(() => act(() => result.current.endDrag(pointer(100)))).not.toThrow()
    expect(result.current.width).toBe(RAIL_DEFAULT_WIDTH + 100)
    spy.mockRestore()
  })

  it('setPointerCapture 不被支持时（老浏览器 / jsdom 替身）不抛', () => {
    const { result } = renderHook(() => useRailWidth(false))
    const throwing = {
      clientX: 10,
      pointerId: 1,
      preventDefault: () => {},
      currentTarget: {
        setPointerCapture() {
          throw new Error('not supported')
        },
        releasePointerCapture() {
          throw new Error('not supported')
        },
      },
    } as never
    expect(() => act(() => result.current.onPointerDown(throwing))).not.toThrow()
    expect(() => act(() => result.current.endDrag(throwing))).not.toThrow()
  })
})
