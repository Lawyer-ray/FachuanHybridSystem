// @vitest-environment jsdom
/**
 * useMediaUrlWithAuth 换票失败降级回归测试。
 *
 * 背景（2026-10 审查 D-P2-5）：withDownloadTicket 失败时会把原 path 原样返回
 * （不带 ticket），直接塞进 iframe 只会得到 403 空白框且永远转圈。
 * 现要求 hook 暴露 failed 标志，让调用方降级。
 */
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const resolveMock = vi.fn()

vi.mock('../domain', () => ({
  resolveMediaUrlWithAuth: (...args: unknown[]) => resolveMock(...args),
}))

import { useMediaUrlWithAuth } from './use-media-url-with-auth'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useMediaUrlWithAuth', () => {
  it('换票成功：返回带 ticket 的 URL 且 failed=false', async () => {
    resolveMock.mockResolvedValue('/api/v1/file/a.pdf?ticket=abc')
    const { result } = renderHook(() => useMediaUrlWithAuth('/media/a.pdf'))

    await waitFor(() => expect(result.current.url).toContain('ticket=abc'))
    expect(result.current.failed).toBe(false)
  })

  it('换票失败（原样返回 path）：failed=true，调用方可降级', async () => {
    resolveMock.mockResolvedValue('/media/a.pdf')
    const { result } = renderHook(() => useMediaUrlWithAuth('/media/a.pdf'))

    await waitFor(() => expect(result.current.failed).toBe(true))
    expect(result.current.url).toBe('/media/a.pdf')
  })

  it('抛出异常：failed=true 且 url 为空', async () => {
    resolveMock.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useMediaUrlWithAuth('/media/a.pdf'))

    await waitFor(() => expect(result.current.failed).toBe(true))
    expect(result.current.url).toBe('')
  })

  it('无 mediaUrl：保持初始空态，不发请求', () => {
    const { result } = renderHook(() => useMediaUrlWithAuth(null))
    expect(result.current).toEqual({ url: '', failed: false })
    expect(resolveMock).not.toHaveBeenCalled()
  })
})
