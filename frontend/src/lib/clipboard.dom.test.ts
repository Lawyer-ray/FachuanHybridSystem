// @vitest-environment jsdom
/**
 * lib/clipboard（copyText）单测（jsdom）。
 * 三条路径：navigator.clipboard 成功；writeText 被拒后 textarea + execCommand 兜底；
 * 两条都失败回 false。不弹 toast（提示留给调用方）由本模块职责决定，无需断言。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { copyText } from './clipboard'

const writeTextMock = vi.fn()
const execCommandMock = vi.fn()

beforeEach(() => {
  writeTextMock.mockReset()
  execCommandMock.mockReset()
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: writeTextMock },
  })
  document.execCommand = execCommandMock
})

afterEach(() => {
  // 还原成「无 clipboard API」以外的默认态由各用例自行设置；这里只清桩计数
  delete (navigator as { clipboard?: unknown }).clipboard
})

describe('copyText', () => {
  it('navigator.clipboard 成功 → true，不走 execCommand', async () => {
    writeTextMock.mockResolvedValue(undefined)
    await expect(copyText('hello')).resolves.toBe(true)
    expect(writeTextMock).toHaveBeenCalledWith('hello')
    expect(execCommandMock).not.toHaveBeenCalled()
  })

  it('writeText 被拒 → 隐藏 textarea + execCommand 兜底；成功 true', async () => {
    writeTextMock.mockRejectedValue(new Error('denied'))
    execCommandMock.mockReturnValue(true)
    await expect(copyText('fallback')).resolves.toBe(true)
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('两条路径都失败 → false', async () => {
    writeTextMock.mockRejectedValue(new Error('denied'))
    execCommandMock.mockReturnValue(false)
    await expect(copyText('nope')).resolves.toBe(false)
  })

  it('无 clipboard API（非安全上下文）→ 直接 execCommand 兜底', async () => {
    delete (navigator as { clipboard?: unknown }).clipboard
    execCommandMock.mockReturnValue(true)
    await expect(copyText('legacy')).resolves.toBe(true)
    expect(execCommandMock).toHaveBeenCalledWith('copy')
  })

  it('execCommand 抛异常（极老浏览器）→ false 且临时节点已移除', async () => {
    delete (navigator as { clipboard?: unknown }).clipboard
    execCommandMock.mockImplementation(() => {
      throw new Error('unsupported')
    })
    await expect(copyText('ancient')).resolves.toBe(false)
    expect(document.querySelectorAll('textarea')).toHaveLength(0)
  })
})
