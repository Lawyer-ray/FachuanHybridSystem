// @vitest-environment jsdom
/**
 * doc-parse-outcome 的 downloadOutcome 单测（jsdom）。
 *
 * outcomeText / copyOutcome 已在 doc-parse-outcome.test.ts（node）覆盖；
 * 本文件只补下载分支：Blob MIME、扩展名（md/txt）、点击后清理与 URL 撤销。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

import { downloadOutcome } from './doc-parse-outcome'

describe('downloadOutcome（前端本地合成下载）', () => {
  let createObjectURL: ReturnType<typeof vi.fn>
  let revokeObjectURL: ReturnType<typeof vi.fn>
  let clickSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    let seq = 0
    createObjectURL = vi.fn(() => `blob:dl-${seq++}`)
    revokeObjectURL = vi.fn()
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  afterEach(() => {
    clickSpy.mockRestore()
    const urlCtor = URL as unknown as Record<string, unknown>
    delete urlCtor.createObjectURL
    delete urlCtor.revokeObjectURL
  })

  it('markdown 内容：text/markdown Blob + .md 文件名，点击后撤销 URL', () => {
    downloadOutcome({ markdown: '# 标题', text: '' }, '解析结果')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    const blob = createObjectURL.mock.calls[0]![0] as Blob
    expect(blob.type).toBe('text/markdown;charset=utf-8')

    const anchor = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement
    expect(anchor.getAttribute('href')).toBe('blob:dl-0')
    expect(anchor.download).toBe('解析结果.md')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:dl-0')
    // 临时锚点已清理
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('纯文本内容（无 markdown）：text/plain + .txt 文件名', () => {
    downloadOutcome({ markdown: '', text: '正文' }, '笔记')
    const blob = createObjectURL.mock.calls[0]![0] as Blob
    expect(blob.type).toBe('text/plain;charset=utf-8')
    const anchor = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement
    expect(anchor.download).toBe('笔记.txt')
  })

  it('空内容：提示且不触发任何下载行为', () => {
    downloadOutcome(null, 'x')
    downloadOutcome({ markdown: '', text: '' }, 'x')
    expect(toast.info).toHaveBeenCalledWith('没有可下载的解析内容')
    expect(toast.info).toHaveBeenCalledTimes(2)
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(clickSpy).not.toHaveBeenCalled()
  })
})
