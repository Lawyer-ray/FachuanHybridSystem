// @vitest-environment jsdom
/**
 * 法院短信文书复制三级降级单测（jsdom）。
 *
 * mock 只打 api 层（../../../api 的后端直写与下载地址）与 sonner toast；
 * 浏览器能力（ClipboardItem / navigator.clipboard / fetch）按用例用
 * vi.stubGlobal 提供可控桩，覆盖「后端直写 → 浏览器写 PDF → 文件名兜底」全链路。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { toastMock, backendCopyMock, fetchMock, writeMock, writeTextMock } = vi.hoisted(() => ({
  toastMock: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
  backendCopyMock: vi.fn(),
  fetchMock: vi.fn(),
  writeMock: vi.fn(),
  writeTextMock: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: toastMock }))

vi.mock('../../../api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  copyCourtSmsDocsToClipboard: backendCopyMock,
}))

import { copyAllDocFiles, copyBlobsToClipboard, copyDocFile, copyTextToClipboard, fetchDocBlob } from './copy-files'

/** 可控的 ClipboardItem 桩：unsupported 里列出的类型构造时抛错（模拟浏览器不支持） */
class FakeClipboardItem {
  static unsupported: string[] = []
  types: string[]
  blobs: Record<string, Blob>
  constructor(map: Record<string, Blob>) {
    for (const t of FakeClipboardItem.unsupported) {
      if (t in map) throw new TypeError(`类型不支持: ${t}`)
    }
    this.types = Object.keys(map)
    this.blobs = map
  }
}

/** Blob 形状桩（断言透传即可，不编解码真实字节） */
const blob = (tag: string) => new Blob([tag], { type: 'application/pdf' })

beforeEach(() => {
  vi.clearAllMocks()
  FakeClipboardItem.unsupported = []
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchDocBlob', () => {
  it('按下载地址取文件：ok 返回 blob；非 2xx 抛「下载失败 HTTP xxx」', async () => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce({ ok: true, blob: async () => blob('a') })
    await expect(fetchDocBlob(3, 0)).resolves.toBeInstanceOf(Blob)
    // 安全审计 M-2：fetch 能带 Authorization 头，故用裸路径而非下载票据
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/automation/court-sms/3/documents/0/download',
      expect.anything(),
    )

    fetchMock.mockResolvedValueOnce({ ok: false, status: 500, blob: async () => blob('x') })
    await expect(fetchDocBlob(3, 1)).rejects.toThrow('下载失败 HTTP 500')
  })
})

describe('copyBlobsToClipboard', () => {
  it('环境无 ClipboardItem（Firefox 等）：直接 false，不触碰剪贴板', async () => {
    vi.stubGlobal('ClipboardItem', undefined)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock } })
    await expect(copyBlobsToClipboard([blob('a')])).resolves.toBe(false)
    expect(writeMock).not.toHaveBeenCalled()
  })

  it('navigator.clipboard.write 缺失：false', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', {})
    await expect(copyBlobsToClipboard([blob('a')])).resolves.toBe(false)
  })

  it('支持标准 application/pdf：构造条目并写入，返回 true', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock } })
    writeMock.mockResolvedValueOnce(undefined)
    const b1 = blob('a')
    const b2 = blob('b')
    await expect(copyBlobsToClipboard([b1, b2])).resolves.toBe(true)
    expect(writeMock).toHaveBeenCalledTimes(1)
    const items = writeMock.mock.calls[0]![0] as FakeClipboardItem[]
    expect(items.map((i) => i.types)).toEqual([['application/pdf'], ['application/pdf']])
    expect(items[0]!.blobs['application/pdf']).toBe(b1)
  })

  it('标准类型不支持时退到 web 前缀自定义格式（旧版 Chromium）', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock } })
    writeMock.mockResolvedValueOnce(undefined)
    FakeClipboardItem.unsupported = ['application/pdf']
    await expect(copyBlobsToClipboard([blob('a')])).resolves.toBe(true)
    const items = writeMock.mock.calls[0]![0] as FakeClipboardItem[]
    expect(items[0]!.types).toEqual(['web application/pdf'])
  })

  it('两类类型都不支持：条目为空、不调 write，返回 false', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock } })
    FakeClipboardItem.unsupported = ['application/pdf', 'web application/pdf']
    await expect(copyBlobsToClipboard([blob('a')])).resolves.toBe(false)
    expect(writeMock).not.toHaveBeenCalled()
  })

  it('clipboard.write 本身抛错（权限被拒等）：吞错返回 false', async () => {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock } })
    writeMock.mockRejectedValueOnce(new Error('NotAllowedError'))
    await expect(copyBlobsToClipboard([blob('a')])).resolves.toBe(false)
  })
})

describe('copyTextToClipboard', () => {
  it('成功 true；writeText 抛错 false（不向上传播）', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: writeTextMock } })
    writeTextMock.mockResolvedValueOnce(undefined)
    await expect(copyTextToClipboard('a.pdf')).resolves.toBe(true)
    expect(writeTextMock).toHaveBeenCalledWith('a.pdf')
    writeTextMock.mockRejectedValueOnce(new Error('NotAllowedError'))
    await expect(copyTextToClipboard('a.pdf')).resolves.toBe(false)
  })
})

describe('copyDocs 三级降级（经 copyDocFile / copyAllDocFiles 入口）', () => {
  function enableBrowserClipboard() {
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('navigator', { clipboard: { write: writeMock, writeText: writeTextMock } })
  }

  it('一级后端直写成功：toast 提示 Finder 语义，不再走浏览器路径', async () => {
    backendCopyMock.mockResolvedValueOnce({ success: true, copied: 2, reason: null })
    await copyDocFile(3, 0, '判决书.pdf')
    expect(backendCopyMock).toHaveBeenCalledWith(3, [0])
    expect(toastMock.success).toHaveBeenCalledWith(
      expect.stringContaining('已复制 2 个文件'),
    )
    expect(fetchMock).not.toHaveBeenCalled()
    expect(writeMock).not.toHaveBeenCalled()
  })

  it('一级不可用（copied=0）：降级浏览器剪贴板，逐件 fetch 后写 PDF 成功', async () => {
    enableBrowserClipboard()
    backendCopyMock.mockResolvedValueOnce({ success: false, copied: 0, reason: 'unsupported' })
    fetchMock.mockImplementation(async (url: string) => ({ ok: true, blob: async () => blob(url) }))
    writeMock.mockResolvedValueOnce(undefined)
    await copyAllDocFiles(3, ['a.pdf', 'b.pdf'])
    // 全部入口：indexes = [0, 1]，两件各取一次
    expect(backendCopyMock).toHaveBeenCalledWith(3, [0, 1])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(writeMock).toHaveBeenCalledTimes(1)
    expect(toastMock.success).toHaveBeenCalledWith(expect.stringContaining('改用打包下载'))
  })

  it('一级网络失败 + 二级取文件失败：落到三级文件名兜底（toast.info）', async () => {
    enableBrowserClipboard()
    backendCopyMock.mockRejectedValueOnce(new Error('后端不可达'))
    fetchMock.mockResolvedValue({ ok: false, status: 404, blob: async () => blob('x') })
    writeTextMock.mockResolvedValueOnce(undefined)
    await copyDocFile(3, 0, '判决书.pdf')
    expect(writeTextMock).toHaveBeenCalledWith('判决书.pdf')
    expect(writeMock).not.toHaveBeenCalled()
    expect(toastMock.info).toHaveBeenCalledWith(expect.stringContaining('已复制文件名'))
  })

  it('三级也失败（writeText 被拒）：toast.error 提示改用下载', async () => {
    enableBrowserClipboard()
    backendCopyMock.mockResolvedValueOnce({ success: false, copied: 0, reason: null })
    fetchMock.mockResolvedValue({ ok: false, status: 500, blob: async () => blob('x') })
    writeTextMock.mockRejectedValueOnce(new Error('NotAllowedError'))
    await copyAllDocFiles(3, ['a.pdf', 'b.pdf'])
    expect(toastMock.error).toHaveBeenCalledWith('复制失败，请改用下载')
  })
})
