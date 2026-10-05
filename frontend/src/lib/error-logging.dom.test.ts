// @vitest-environment jsdom
/**
 * lib/error-logging 单测（jsdom）。
 *
 * setupGlobalErrorLogging 在 window 上挂 unhandledrejection / error 监听，
 * 结构化前缀输出；重复调用幂等。用真实事件分发驱动监听器，spy console.error
 * 断言上报格式。
 */
import { describe, expect, it, vi } from 'vitest'

import { setupGlobalErrorLogging } from './error-logging'

describe('setupGlobalErrorLogging', () => {
  it('unhandledrejection / error 事件 → 结构化前缀输出（reason / e.error ?? message）', () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    setupGlobalErrorLogging()

    const rejection = new Event('unhandledrejection')
    Object.defineProperty(rejection, 'reason', { value: { boom: 1 } })
    window.dispatchEvent(rejection)
    expect(errSpy).toHaveBeenCalledWith('[unhandled] rejection:', { boom: 1 })

    const withError = new Event('error')
    const err = new Error('boom')
    Object.defineProperty(withError, 'error', { value: err })
    window.dispatchEvent(withError)
    expect(errSpy).toHaveBeenCalledWith('[unhandled] error:', err)

    // ResourceError 类事件只有 message、没有 error 字段 → 回退 message
    const msgOnly = new Event('error')
    Object.defineProperty(msgOnly, 'message', { value: 'script load failed' })
    window.dispatchEvent(msgOnly)
    expect(errSpy).toHaveBeenCalledWith('[unhandled] error:', 'script load failed')

    expect(errSpy).toHaveBeenCalledTimes(3)
    errSpy.mockRestore()
  })

  it('重复调用幂等：不会重复挂监听（一次事件只上报一次）', () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    setupGlobalErrorLogging()
    setupGlobalErrorLogging()

    const rejection = new Event('unhandledrejection')
    Object.defineProperty(rejection, 'reason', { value: 'again' })
    window.dispatchEvent(rejection)

    expect(errSpy).toHaveBeenCalledTimes(1)
    errSpy.mockRestore()
  })
})
