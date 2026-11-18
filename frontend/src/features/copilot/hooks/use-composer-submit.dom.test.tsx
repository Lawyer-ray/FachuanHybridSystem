// @vitest-environment jsdom
/**
 * useComposerSubmit 测试（jsdom）。
 *
 * 锁的是从 Composer 拆出来后最容易漂的两件事：
 * 1. 发送路径的分流顺序：流式中 Enter 是「插话」不是「新消息」；slash 菜单开着
 *    时 Enter 是「选中菜单项」，绝不能同时把半句话发出去。
 * 2. IME 接线（PIT-006）：合成中 / compositionend 后 80ms 内的 Enter 一律吞掉，
 *    且必须在 slash 之前短路 —— 否则选词那次 Enter 会顺带选中菜单项或直接发送。
 *
 * 事件对象手建 plain object 强转（同 use-ime-enter-guard.dom.test.tsx）：尾随窗口
 * 靠 timeStamp 精确定位，jsdom 的 KeyboardEvent.timeStamp 是只读高精度时间，设不了
 * 「compositionend 后第 10ms」这种值。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { POST_COMPOSITION_ENTER_GUARD_MS } from './use-ime-enter-guard'
import { useComposerSubmit, type ComposerSubmitOptions } from './use-composer-submit'

/** 极简键盘事件替身：timeStamp / keyCode / isComposing 全部可控 */
function keyEvent(
  key: string,
  opts: { timeStamp?: number; keyCode?: number; isComposing?: boolean; shiftKey?: boolean } = {},
) {
  return {
    key,
    shiftKey: opts.shiftKey ?? false,
    timeStamp: opts.timeStamp ?? 0,
    keyCode: opts.keyCode ?? 0,
    preventDefault: vi.fn(),
    nativeEvent: { isComposing: opts.isComposing ?? false },
  } as unknown as React.KeyboardEvent<HTMLTextAreaElement>
}

/** 带 mock 的完整 options；默认值为「有正文、空闲、非流式、非后台」 */
function makeOptions(overrides: Partial<ComposerSubmitOptions> = {}): ComposerSubmitOptions {
  return {
    text: '你好',
    setText: vi.fn(),
    textareaRef: { current: null },
    pendingFiles: [],
    pendingRefs: [],
    pendingQuote: null,
    uploading: false,
    sending: false,
    streaming: false,
    bgMode: false,
    setBgMode: vi.fn(),
    speech: { listening: false, stop: vi.fn() },
    slash: { onKeyDown: vi.fn(() => false) },
    send: vi.fn(async () => {}),
    steer: vi.fn(async () => {}),
    submitTask: vi.fn(async () => {}),
    ...overrides,
  }
}

function render(options: ComposerSubmitOptions) {
  return renderHook(() => useComposerSubmit(options))
}

/** 走一遍 compositionend，并把尾随窗口的基准时间戳定在 `at` */
function endComposition(
  hook: ReturnType<typeof useComposerSubmit>,
  at: number,
) {
  act(() => {
    hook.onCompositionEnd({ timeStamp: at } as unknown as React.CompositionEvent<HTMLTextAreaElement>)
  })
}

function startComposition(hook: ReturnType<typeof useComposerSubmit>) {
  act(() => {
    hook.onCompositionStart()
  })
}

function press(hook: ReturnType<typeof useComposerSubmit>, e: React.KeyboardEvent<HTMLTextAreaElement>) {
  act(() => {
    hook.handleKeyDown(e)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useComposerSubmit：Enter 与 Shift+Enter', () => {
  it('普通 Enter 发送，并 preventDefault', () => {
    const options = makeOptions()
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000 })

    press(result.current, e)

    expect(options.send).toHaveBeenCalledTimes(1)
    expect(options.send).toHaveBeenCalledWith('你好', expect.any(Function))
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
    // 先清空正文腾出输入位，再发
    expect(options.setText).toHaveBeenCalledWith('')
  })

  it('Shift+Enter 不发送（换行），也不 preventDefault', () => {
    const options = makeOptions()
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000, shiftKey: true })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
    // 换行不是菜单键，slash 也不该被问
    expect(options.slash.onKeyDown).not.toHaveBeenCalled()
  })
})

describe('useComposerSubmit：IME 合成中的 Enter', () => {
  it('compositionstart 之后 Enter 不发送，且不 preventDefault（留给输入法上屏）', () => {
    const options = makeOptions()
    const { result } = render(options)
    startComposition(result.current)
    const e = keyEvent('Enter', { timeStamp: 5000 })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(options.setText).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('nativeEvent.isComposing 为 true 时 Enter 不发送', () => {
    const options = makeOptions()
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000, isComposing: true })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('keyCode 229 的 Enter 不发送（不派发 composition 事件的输入法）', () => {
    const options = makeOptions()
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000, keyCode: 229 })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('合成中的 Shift+Enter 也被吞掉（是输入法行为，不是换行）', () => {
    const options = makeOptions()
    const { result } = render(options)
    startComposition(result.current)
    const e = keyEvent('Enter', { timeStamp: 5000, shiftKey: true })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
})

describe('useComposerSubmit：compositionend 之后的尾随 Enter（PIT-006 回归）', () => {
  it('80ms 内的 Enter 不发送，并 preventDefault 吞掉默认行为', () => {
    const options = makeOptions()
    const { result } = render(options)
    startComposition(result.current)
    endComposition(result.current, 6000)
    const e = keyEvent('Enter', { timeStamp: 6000 + 10 })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(options.setText).not.toHaveBeenCalled()
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('正好 80ms 边界仍被吞掉', () => {
    const options = makeOptions()
    const { result } = render(options)
    endComposition(result.current, 6000)
    const e = keyEvent('Enter', {
      timeStamp: 6000 + POST_COMPOSITION_ENTER_GUARD_MS,
    })

    press(result.current, e)

    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('超过 80ms 的 Enter 正常发送（用户真的又按了一次）', () => {
    const options = makeOptions()
    const { result } = render(options)
    endComposition(result.current, 6000)
    const e = keyEvent('Enter', {
      timeStamp: 6000 + POST_COMPOSITION_ENTER_GUARD_MS + 1,
    })

    press(result.current, e)

    expect(options.send).toHaveBeenCalledTimes(1)
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })
})

describe('useComposerSubmit：slash 菜单与 IME 的先后顺序', () => {
  it('菜单开着时 Enter 走 slash 分支：选中菜单项，不发送', () => {
    const options = makeOptions()
    const slashOnKeyDown = vi.mocked(options.slash.onKeyDown)
    slashOnKeyDown.mockReturnValue(true)
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000 })

    press(result.current, e)

    expect(slashOnKeyDown).toHaveBeenCalledTimes(1)
    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('合成中的 Enter 在 slash 之前就被拦：菜单不会被选词 Enter 选中', () => {
    const options = makeOptions()
    const slashOnKeyDown = vi.mocked(options.slash.onKeyDown)
    slashOnKeyDown.mockReturnValue(true)
    const { result } = render(options)
    startComposition(result.current)
    const e = keyEvent('Enter', { timeStamp: 5000 })

    press(result.current, e)

    expect(slashOnKeyDown).not.toHaveBeenCalled()
    expect(options.send).not.toHaveBeenCalled()
    // 合成中不 preventDefault（留给输入法），也不该顺带确认菜单
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('compositionend 尾随窗口内的 Enter 同样不进入 slash 分支', () => {
    const options = makeOptions()
    const slashOnKeyDown = vi.mocked(options.slash.onKeyDown)
    slashOnKeyDown.mockReturnValue(true)
    const { result } = render(options)
    endComposition(result.current, 6000)
    const e = keyEvent('Enter', { timeStamp: 6000 + 5 })

    press(result.current, e)

    expect(slashOnKeyDown).not.toHaveBeenCalled()
    expect(options.send).not.toHaveBeenCalled()
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })
})

describe('useComposerSubmit：流式中 Enter 是插话', () => {
  it('流式中 Enter 走 steer 而非 send，并清空草稿', () => {
    const options = makeOptions({ streaming: true })
    const { result } = render(options)
    const e = keyEvent('Enter', { timeStamp: 5000 })

    press(result.current, e)

    expect(options.steer).toHaveBeenCalledWith('你好')
    expect(options.send).not.toHaveBeenCalled()
    expect(options.setText).toHaveBeenCalledWith('')
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('流式中合成态的 Enter 不插话（选词不等于发插话）', () => {
    const options = makeOptions({ streaming: true })
    const { result } = render(options)
    startComposition(result.current)

    press(result.current, keyEvent('Enter', { timeStamp: 5000 }))

    expect(options.steer).not.toHaveBeenCalled()
  })
})
