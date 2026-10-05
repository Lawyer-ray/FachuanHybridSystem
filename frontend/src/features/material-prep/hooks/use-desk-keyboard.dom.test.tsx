// @vitest-environment jsdom
/**
 * useDeskKeyboard 单测（jsdom）。
 *
 * DeskPage 网格键盘导航：←→ 移、↑↓ 按 CSS grid 列数跳行、Space/Enter 打开、
 * X 不接。用 window keydown 事件驱动；getComputedStyle 桩出 3 列网格。
 * 断言聚焦：setSel 收到纯 updater（按入参算边界钳制）、openAt/judge 的
 * 分发、阅读器打开 / 焦点在输入框 / 空列表三种短路。
 */
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { InboxMessage } from '../types'
import { useDeskKeyboard } from './use-desk-keyboard'

function pack(id: number): InboxMessage {
  return { id } as InboxMessage
}

function setup(over: Partial<Parameters<typeof useDeskKeyboard>[0]> = {}) {
  const setSel = vi.fn()
  const openAt = vi.fn()
  const judge = vi.fn()
  const grid = document.createElement('div')
  document.body.appendChild(grid)
  const gridRef = { current: grid }
  const props = {
    visible: [pack(1), pack(2), pack(3), pack(4), pack(5), pack(6)],
    openId: null,
    sel: 0,
    setSel,
    openAt,
    judge,
    gridRef,
    ...over,
  }
  const hook = renderHook((p: typeof props) => useDeskKeyboard(p), { initialProps: props })
  return { ...hook, setSel, openAt, judge, props }
}

/** 派发 keydown（cancelable 便于断言 preventDefault），返回事件 */
function press(key: string, target?: HTMLElement) {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  ;(target ?? window).dispatchEvent(e)
  return e
}

beforeEach(() => {
  // 桩出 3 列网格（↑↓ 按列数跳行）
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({ gridTemplateColumns: 'a a a' } as unknown as CSSStyleDeclaration)
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('useDeskKeyboard（移动与边界）', () => {
  it.each([
    ['ArrowRight', 0, 1],
    ['ArrowRight', 5, 5], // 已在末位：钳制不动
    ['ArrowLeft', 5, 4],
    ['ArrowLeft', 0, 0], // 已在首位：钳制不动
    ['ArrowDown', 0, 3], // 3 列网格：跳一行
    ['ArrowDown', 4, 5], // 跳行后钳到末位
    ['ArrowUp', 5, 2],
    ['ArrowUp', 1, 0], // 减一整行后钳到 0
  ])('%s：sel=%d → %d（并 preventDefault）', (key, from, to) => {
    const r = setup({ sel: from })
    const e = press(key)
    expect(e.defaultPrevented).toBe(true)
    expect(r.setSel).toHaveBeenCalledTimes(1)
    const updater = r.setSel.mock.calls[0]![0] as (s: number) => number
    expect(updater(from)).toBe(to)
  })

  it('grid ref 缺失（列表未挂载）：按 1 列处理', () => {
    vi.restoreAllMocks()
    const r = setup({ gridRef: { current: null }, sel: 0 })
    press('ArrowDown')
    const updater = r.setSel.mock.calls[0]![0] as (s: number) => number
    expect(updater(0)).toBe(1)
  })
})

describe('useDeskKeyboard（动作键）', () => {
  it('Space / Enter：打开当前选中包', () => {
    const r = setup({ sel: 2 })
    const e1 = press(' ')
    expect(r.openAt).toHaveBeenCalledWith(2)
    expect(e1.defaultPrevented).toBe(true)

    press('Enter')
    expect(r.openAt).toHaveBeenCalledTimes(2)
  })

  it('x / X：对当前选中包下发「不接」判定', () => {
    const r = setup({ sel: 1 })
    press('x')
    press('X')
    expect(r.judge).toHaveBeenCalledTimes(2)
    expect(r.judge).toHaveBeenCalledWith({ id: 2 }, 'filed')
    // 判定不 preventDefault（不影响页面滚动等默认行为）
    expect(r.setSel).not.toHaveBeenCalled()
  })
})

describe('useDeskKeyboard（短路分支）', () => {
  it('阅读器打开（openId != null）：全部按键忽略', () => {
    const r = setup({ openId: 7 })
    press('ArrowRight')
    press('Enter')
    press('x')
    expect(r.setSel).not.toHaveBeenCalled()
    expect(r.openAt).not.toHaveBeenCalled()
    expect(r.judge).not.toHaveBeenCalled()
  })

  it('焦点在 input / textarea / select 内：不劫持按键', () => {
    const r = setup()
    const input = document.createElement('input')
    document.body.appendChild(input)
    press('ArrowRight', input)
    expect(r.setSel).not.toHaveBeenCalled()

    const wrap = document.createElement('div')
    const textarea = document.createElement('textarea')
    wrap.appendChild(textarea)
    document.body.appendChild(wrap)
    press('Enter', textarea)
    expect(r.openAt).not.toHaveBeenCalled()
  })

  it('空列表：按键无动作', () => {
    const r = setup({ visible: [] })
    press('ArrowRight')
    press('Enter')
    expect(r.setSel).not.toHaveBeenCalled()
    expect(r.openAt).not.toHaveBeenCalled()
  })

  it('sel 越界时 X 不误判（visible[sel] 缺失即跳过）', () => {
    const r = setup({ sel: 99 })
    press('x')
    expect(r.judge).not.toHaveBeenCalled()
  })
})
