// @vitest-environment jsdom
/**
 * PhotoPageView 测试（jsdom）。
 *
 * 图片页渲染：加载中占位、成功后用 objectURL 渲染 img、失败显示可读错误、
 * 卸载时 revoke objectURL（防泄漏），卸载后才回来的结果也要就地 revoke。
 */
import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ fetchAttachmentBytes: vi.fn() }))
vi.mock('../../api', () => ({ fetchAttachmentBytes: apiMock.fetchAttachmentBytes }))

import { PhotoPageView } from './PhotoPageView'

let createSpy: ReturnType<typeof vi.fn>
let revokeSpy: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.fetchAttachmentBytes.mockResolvedValue(new Uint8Array([1, 2, 3]))
  createSpy = vi.fn(() => 'blob:mock-url')
  revokeSpy = vi.fn()
  URL.createObjectURL = createSpy as never
  URL.revokeObjectURL = revokeSpy as never
})

describe('PhotoPageView：加载态', () => {
  it('初始显示占位图标', () => {
    apiMock.fetchAttachmentBytes.mockReturnValue(new Promise(() => {}))
    const { container } = render(<PhotoPageView messageId={1} partIndex={0} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).toBeTruthy()
    container.remove()
  })

  it('按入参请求字节', async () => {
    const { container } = render(<PhotoPageView messageId={7} partIndex={3} />)
    await waitFor(() => expect(apiMock.fetchAttachmentBytes).toHaveBeenCalledWith(7, 3))
    container.remove()
  })
})

describe('PhotoPageView：成功与失败', () => {
  it('成功后渲染 img，src 为 objectURL', async () => {
    const { container } = render(<PhotoPageView messageId={1} partIndex={0} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())
    expect(container.querySelector('img')!.getAttribute('src')).toBe('blob:mock-url')
    expect(container.querySelector('img')!.getAttribute('alt')).toBe('材料页')
    container.remove()
  })

  it('请求失败显示可读错误（不静默吞掉）', async () => {
    apiMock.fetchAttachmentBytes.mockRejectedValue(new Error('404'))
    const { container } = render(<PhotoPageView messageId={1} partIndex={0} />)
    await waitFor(() => expect(container.textContent).toContain('该页加载失败'))
    container.remove()
  })
})

describe('PhotoPageView：objectURL 生命周期', () => {
  it('卸载时 revoke 已创建的 objectURL', async () => {
    const { container, unmount } = render(<PhotoPageView messageId={1} partIndex={0} />)
    await waitFor(() => expect(container.querySelector('img')).toBeTruthy())

    unmount()
    expect(revokeSpy).toHaveBeenCalledWith('blob:mock-url')
  })

  it('卸载后才回来的结果：就地 revoke 且不写入 state', async () => {
    let resolveBytes: (v: Uint8Array) => void = () => {}
    apiMock.fetchAttachmentBytes.mockReturnValue(
      new Promise<Uint8Array>((r) => {
        resolveBytes = r
      }),
    )

    const { container, unmount } = render(<PhotoPageView messageId={1} partIndex={0} />)
    unmount()
    resolveBytes(new Uint8Array([9]))

    await waitFor(() => expect(revokeSpy).toHaveBeenCalledWith('blob:mock-url'))
    container.remove()
  })
})
