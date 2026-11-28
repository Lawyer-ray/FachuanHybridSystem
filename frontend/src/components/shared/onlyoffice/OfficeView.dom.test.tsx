// @vitest-environment jsdom
/**
 * OfficeView 单测（jsdom）。
 *
 * 契约：
 * - 配置来自后端（getEditorConfig），前端不持有 DS 密钥；
 * - 未启用（enabled=false）→ 显示「未启用」，不加载 api.js；
 * - 正常路径 → 加载 api.js 后把 config 交给 DocsAPI.DocEditor；
 * - 卸载时必须 destroyEditor，否则 DS iframe 残留。
 */
import { fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getEditorConfig = vi.fn()
vi.mock('./api', () => ({
  getEditorConfig: (...args: unknown[]) => getEditorConfig(...args),
}))

import { OfficeView } from './OfficeView'

type DocEditorCtor = new (
  host: string | HTMLElement,
  config: Record<string, unknown>,
) => { destroyEditor?: () => void }

const CONFIG = { documentType: 'word', token: 'signed-token', document: { key: 'k1' } }

beforeEach(() => {
  getEditorConfig.mockReset()
  delete (window as { DocsAPI?: unknown }).DocsAPI
})

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as { DocsAPI?: unknown }).DocsAPI
  document.head.querySelectorAll('script[src*="documents/api.js"]').forEach((el) => el.remove())
})

describe('OfficeView', () => {
  it('未启用时显示未启用提示，且不加载 api.js', async () => {
    getEditorConfig.mockResolvedValue({
      enabled: false,
      docserver_url: '',
      config: null,
      reason: 'OnlyOffice 未配置',
    })

    const { findByText } = render(<OfficeView fileUrl="/api/v1/inbox/x" fileName="a.docx" />)

    expect(await findByText('OnlyOffice 未启用')).toBeTruthy()
    expect(await findByText('OnlyOffice 未配置')).toBeTruthy()
    expect(window.DocsAPI).toBeUndefined()
  })

  it('正常路径：拉配置后把签名 config 交给 DocEditor', async () => {
    const instance = { destroyEditor: vi.fn() }
    const docEditor = vi.fn(function DocEditorMock() {
      return instance
    })
    // DocsAPI 已就绪时不应再注入 api.js（同页多实例共用一份）
    window.DocsAPI = { DocEditor: docEditor as unknown as DocEditorCtor }
    getEditorConfig.mockResolvedValue({
      enabled: true,
      docserver_url: 'http://ds.local',
      config: CONFIG,
      reason: '',
    })

    const { container } = render(
      <OfficeView fileUrl="/api/v1/inbox/x" fileName="a.docx" mode="review" version="v2" />,
    )

    await waitFor(() => {
      expect(getEditorConfig).toHaveBeenCalledWith('/api/v1/inbox/x', 'a.docx', 'review', 'v2')
    })
    await waitFor(() => expect(docEditor).toHaveBeenCalled())

    // config 原样交给 DS（含后端签名的 token，前端没见过密钥）
    const passed = docEditor.mock.calls[0] as unknown as [HTMLElement, Record<string, unknown>]
    expect(passed[1]).toMatchObject({ documentType: 'word', token: 'signed-token' })
    expect(container.querySelector('div div')).toBeTruthy()
  })

  it('画布改动事件转给父级（关文档前要不要拦，全靠它）', async () => {
    const docEditor = vi.fn(function DocEditorMock() {
      return {}
    })
    window.DocsAPI = { DocEditor: docEditor as unknown as DocEditorCtor }
    getEditorConfig.mockResolvedValue({
      enabled: true,
      docserver_url: 'http://ds.local',
      config: CONFIG,
      reason: '',
    })
    const onDirtyChange = vi.fn()
    render(<OfficeView fileUrl="/api/v1/inbox/x" fileName="a.docx" onDirtyChange={onDirtyChange} />)
    await waitFor(() => expect(docEditor).toHaveBeenCalled())

    const events = (docEditor.mock.calls[0] as unknown as [HTMLElement, { events: Record<string, (e?: unknown) => void> }])[1].events
    // 各 DS 版本口径不同：event.data 有时是布尔，有时是 { status }
    expect(typeof events.onDocumentStateChange).toBe('function')
    events.onDocumentStateChange!({ data: true })
    events.onDocumentStateChange!({ data: { status: false } })

    expect(onDirtyChange.mock.calls.map((c) => c[0])).toEqual([true, false])
  })

  it('打开失败时给「重试」并重新签配置（原先只能关掉文件再点开）', async () => {
    const docEditor = vi.fn(function DocEditorMock() {
      return {}
    })
    window.DocsAPI = { DocEditor: docEditor as unknown as DocEditorCtor }
    getEditorConfig.mockResolvedValue({
      enabled: true,
      docserver_url: 'http://ds.local',
      config: CONFIG,
      reason: '',
    })
    const onStateChange = vi.fn()
    const { findByText } = render(
      <OfficeView fileUrl="/api/v1/inbox/x" fileName="a.docx" onStateChange={onStateChange} />,
    )
    await waitFor(() => expect(docEditor).toHaveBeenCalled())

    const events = (docEditor.mock.calls[0] as unknown as [HTMLElement, { events: Record<string, (e?: unknown, d?: unknown) => void> }])[1].events
    events.onError!({}, { errorDescription: '下载失败' })

    expect(await findByText('文档打开失败')).toBeTruthy()
    expect(await findByText('下载失败')).toBeTruthy()
    expect(onStateChange).toHaveBeenCalledWith('error')

    const before = getEditorConfig.mock.calls.length
    fireEvent.click(await findByText('重试'))
    await waitFor(() => expect(getEditorConfig.mock.calls.length).toBeGreaterThan(before))
  })

  it('卸载时调用 destroyEditor', async () => {
    const destroy = vi.fn()
    const docEditor = vi.fn(function DocEditorMock() {
      return { destroyEditor: destroy }
    })
    window.DocsAPI = { DocEditor: docEditor as unknown as DocEditorCtor }
    getEditorConfig.mockResolvedValue({
      enabled: true,
      docserver_url: 'http://ds.local',
      config: CONFIG,
      reason: '',
    })

    const { unmount, container } = render(<OfficeView fileUrl="/api/v1/inbox/x" fileName="a.docx" />)

    await waitFor(() => expect(docEditor).toHaveBeenCalled())
    expect(container.querySelector('div div')).toBeTruthy()
    unmount()
    expect(destroy).toHaveBeenCalled()
  })
})
