// @vitest-environment jsdom
/**
 * beginDrag 单测（jsdom）。
 *
 * 这段外壳被三处拖拽共用（workbench 分栏、copilot 面板、copilot 侧栏，
 * document-recognition 的分屏/弹窗拖拽也走它），所以它自己的不变量值得单独钉住：
 * - 拖拽期间禁选中 + 换光标；结束后**还原原值**而不是清空
 * - blockIframes 只在开启时动 iframe，且各自按原值还回去
 * - pointercancel 与 pointerup 等价收尾（触摸被系统手势打断不能留残留样式）
 * - 收尾只跑一次，up 之后再来 cancel 不会重复通知
 * - 返回的清理函数是「还活着就收尾」，可重复调用
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { beginDrag } from './drag-listeners'

function pointerEvent(type: string, clientX = 0) {
  const e = new Event(type) as Event & { clientX?: number }
  e.clientX = clientX
  return e
}

beforeEach(() => {
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
})

afterEach(() => {
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  document.querySelectorAll('iframe').forEach((f) => f.remove())
})

describe('beginDrag：拖拽外壳', () => {
  it('拖拽期间禁选中、设 col-resize 光标；结束后复位', () => {
    const cleanup = beginDrag(() => {}, () => {})
    expect(document.body.style.userSelect).toBe('none')
    expect(document.body.style.cursor).toBe('col-resize')

    cleanup()
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('自定义光标生效', () => {
    const cleanup = beginDrag(() => {}, () => {}, { cursor: 'row-resize' })
    expect(document.body.style.cursor).toBe('row-resize')
    cleanup()
  })

  it('结束后还原原值而不是清空（不抹掉页面上已有的内联样式）', () => {
    document.body.style.userSelect = 'text'
    document.body.style.cursor = 'progress'

    const cleanup = beginDrag(() => {}, () => {})
    expect(document.body.style.userSelect).toBe('none')
    expect(document.body.style.cursor).toBe('col-resize')

    cleanup()
    expect(document.body.style.userSelect).toBe('text')
    expect(document.body.style.cursor).toBe('progress')
  })

  it('blockIframes：拖拽期间 iframe 不接收指针事件，结束后按原值还原', () => {
    const a = document.createElement('iframe')
    const b = document.createElement('iframe')
    b.style.pointerEvents = 'auto'
    document.body.append(a, b)

    const cleanup = beginDrag(() => {}, () => {}, { blockIframes: true })
    expect(a.style.pointerEvents).toBe('none')
    expect(b.style.pointerEvents).toBe('none')

    cleanup()
    expect(a.style.pointerEvents).toBe('')
    expect(b.style.pointerEvents).toBe('auto')
  })

  it('不开 blockIframes 时不动 iframe（不拖跨 iframe 的场景没必要改别人样式）', () => {
    const frame = document.createElement('iframe')
    document.body.append(frame)

    const cleanup = beginDrag(() => {}, () => {})
    expect(frame.style.pointerEvents).toBe('')
    cleanup()
  })
})

describe('beginDrag：事件与收尾', () => {
  it('pointermove 逐个转发给 onMove', () => {
    const onMove = vi.fn()
    const cleanup = beginDrag(onMove, () => {})

    window.dispatchEvent(pointerEvent('pointermove', 120))
    window.dispatchEvent(pointerEvent('pointermove', 240))

    expect(onMove).toHaveBeenCalledTimes(2)
    expect((onMove.mock.calls[0]![0] as MouseEvent).clientX).toBe(120)
    expect((onMove.mock.calls[1]![0] as MouseEvent).clientX).toBe(240)
    cleanup()
  })

  it('mousemove 同样转发（老调用方仍用 mouse 事件）', () => {
    const onMove = vi.fn()
    const cleanup = beginDrag(onMove, () => {})

    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 80 }))

    expect(onMove).toHaveBeenCalledTimes(1)
    cleanup()
  })

  it('pointerup 收尾：通知 onEnd 并卸掉监听', () => {
    const onMove = vi.fn()
    const onEnd = vi.fn()
    beginDrag(onMove, onEnd)

    window.dispatchEvent(pointerEvent('pointerup'))
    expect(onEnd).toHaveBeenCalledTimes(1)
    expect(document.body.style.userSelect).toBe('')

    // 已结束：后续移动不再转发
    window.dispatchEvent(pointerEvent('pointermove', 10))
    expect(onMove).not.toHaveBeenCalled()
  })

  it('pointercancel 与 pointerup 等价收尾（触摸被系统手势打断）', () => {
    const onEnd = vi.fn()
    beginDrag(() => {}, onEnd, { blockIframes: true })
    const frame = document.createElement('iframe')
    // 拖拽开始后才出现的 iframe 不归本次收尾管（开始时就已定格名单）
    document.body.append(frame)
    expect(frame.style.pointerEvents).toBe('')

    window.dispatchEvent(pointerEvent('pointercancel'))

    expect(onEnd).toHaveBeenCalledTimes(1)
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('收尾只跑一次：up 之后再来 cancel 不重复通知', () => {
    const onEnd = vi.fn()
    beginDrag(() => {}, onEnd)

    window.dispatchEvent(pointerEvent('pointerup'))
    window.dispatchEvent(pointerEvent('pointercancel'))

    expect(onEnd).toHaveBeenCalledTimes(1)
  })

  it('返回的清理函数在拖拽仍进行时也会收尾（卸载场景）', () => {
    const onEnd = vi.fn()
    const cleanup = beginDrag(() => {}, onEnd)
    expect(document.body.style.userSelect).toBe('none')

    cleanup()

    expect(onEnd).toHaveBeenCalledTimes(1)
    expect(document.body.style.userSelect).toBe('')
    // 幂等：再调一次不重复通知
    cleanup()
    expect(onEnd).toHaveBeenCalledTimes(1)
  })

  it('已正常结束后再调清理函数：不重复通知', () => {
    const onEnd = vi.fn()
    const cleanup = beginDrag(() => {}, onEnd)
    window.dispatchEvent(pointerEvent('pointerup'))
    cleanup()
    expect(onEnd).toHaveBeenCalledTimes(1)
  })
})
