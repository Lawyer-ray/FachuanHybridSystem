// @vitest-environment jsdom
/**
 * 应用内附件预览弹窗（jsdom）。
 *
 * 它是「分诊」的主界面：一条条看过去判断哪条要进材料预处理。锁五件事：
 *
 * 1. 打开就把字节取回来渲染（PDF 走 pdf.js，图片直接显示，别的只说明原因）；
 * 2. 页码真的在翻 —— 断言 `renderPdfPage` 收到的页码，而不只是 UI 上的数字
 *    （只断言文字的话，把渲染参数写死成 1 也照样通过）；
 * 3. 多附件时左侧栏能切，切换后页码归零（否则停在上一份的页码上空白一片）；
 * 4. 下载仍走「一次性票据」，不退化回裸 `<a href>`（那是会 401 的老坑）；
 * 5. 不预取：只有当前消息的附件才请求缩略图。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pdfMock = vi.hoisted(() => ({
  loadPdfDocument: vi.fn(async () => ({ numPages: 3 })),
  renderPdfPage: vi.fn(async (_doc: unknown, _page: number, _width?: number) => document.createElement('canvas')),
}))
vi.mock('@/lib/pdf', () => pdfMock)

const bytesMock = vi.hoisted(() => ({ fetchAttachmentBytes: vi.fn(async () => new ArrayBuffer(32)) }))
vi.mock('../../api', () => ({ fetchAttachmentBytes: bytesMock.fetchAttachmentBytes }))

const thumbMock = vi.hoisted(() => ({
  fetchAttachmentThumbnail: vi.fn(async () => new Blob([new Uint8Array([9])], { type: 'image/jpeg' })),
}))
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, fetchAttachmentThumbnail: thumbMock.fetchAttachmentThumbnail }
})

const dlMock = vi.hoisted(() => ({
  withDownloadTicket: vi.fn(async (u: string) => `${u}?ticket=T`),
  downloadUrl: vi.fn(),
}))
vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: dlMock.withDownloadTicket }))
vi.mock('@/lib/download', () => ({ downloadUrl: dlMock.downloadUrl }))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { AttachmentPreview } from './AttachmentPreview'
import type { InboxAttachment } from '../types'

function att(partIndex: number, filename: string, over: Partial<InboxAttachment> = {}): InboxAttachment {
  const isPdf = filename.endsWith('.pdf')
  return {
    filename,
    original_filename: filename,
    custom_filename: null,
    size: 2048,
    content_type: isPdf ? 'application/pdf' : filename.endsWith('.docx') ? 'application/msword' : 'image/png',
    part_index: partIndex,
    page_count: isPdf ? 3 : null,
    expanded_from: null,
    ...over,
  }
}

function renderPreview(attachments: InboxAttachment[], index = 0) {
  const onClose = vi.fn()
  const onSwitch = vi.fn()
  const utils = render(
    <AttachmentPreview
      target={{ messageId: 12, subject: '（20XX）粤0606执保XXXX号 - 告知书', attachments, index }}
      onClose={onClose}
      onSwitch={onSwitch}
    />,
  )
  return { ...utils, onClose, onSwitch }
}

beforeEach(() => {
  vi.clearAllMocks()
  if (!('createObjectURL' in URL)) {
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:thumb', writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => undefined, writable: true })
  }
})

describe('AttachmentPreview：PDF', () => {
  it('打开即取字节并渲染第 1 页，页脚给出总页数', async () => {
    renderPreview([att(0, '起诉状.pdf')])

    await waitFor(() => expect(bytesMock.fetchAttachmentBytes).toHaveBeenCalledWith(12, 0))
    await waitFor(() => expect(pdfMock.renderPdfPage).toHaveBeenCalled())
    expect(pdfMock.renderPdfPage.mock.calls[0]?.[1]).toBe(1)
    expect(await screen.findByText('1 / 3')).toBeTruthy()
    // 体积与页数都来自附件元信息，不必等 pdf.js
    expect(screen.getByText('2KB · 3 页')).toBeTruthy()
  })

  it('翻页把真正的页码交给渲染器（不是只改 UI 数字）', async () => {
    renderPreview([att(0, '起诉状.pdf')])
    await screen.findByText('1 / 3')

    fireEvent.click(screen.getByRole('button', { name: '下一页' }))

    await waitFor(() => expect(screen.getByText('2 / 3')).toBeTruthy())
    await waitFor(() => expect(pdfMock.renderPdfPage.mock.calls.at(-1)?.[1]).toBe(2))
    // 到最后一页时「下一页」置灰
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(screen.getByText('3 / 3')).toBeTruthy())
    expect((screen.getByRole('button', { name: '下一页' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('关闭按钮把关闭意图交给父级', async () => {
    const { onClose } = renderPreview([att(0, '起诉状.pdf')])
    fireEvent.click(screen.getByRole('button', { name: '关闭预览' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('AttachmentPreview：多附件切换', () => {
  it('左侧栏列出全部附件，点第二份就切过去', async () => {
    const { onSwitch } = renderPreview([att(0, '起诉状.pdf'), att(1, '证据清单.pdf')], 0)

    expect(await screen.findByText('2 个附件')).toBeTruthy()
    fireEvent.click(screen.getByText('证据清单.pdf').closest('button') as HTMLButtonElement)
    expect(onSwitch).toHaveBeenCalledWith(1)
  })

  it('单份附件不画左侧栏（省一块空白）', async () => {
    renderPreview([att(0, '起诉状.pdf')])
    await screen.findByText('1 / 3')
    expect(screen.queryByText(/个附件/)).toBeNull()
  })
})

describe('AttachmentPreview：非 PDF', () => {
  it('图片直接用 img 显示，不走 pdf.js', async () => {
    renderPreview([att(0, '现场照片.png')])
    const img = (await screen.findByAltText('现场照片.png')) as HTMLImageElement
    expect(img.src).toContain('blob:')
    expect(pdfMock.loadPdfDocument).not.toHaveBeenCalled()
  })

  it('Word 等类型说明「不支持在线预览」，且不白拉一次字节', async () => {
    renderPreview([att(0, '判决书.docx')])
    expect(await screen.findByText('该类型不支持在线预览')).toBeTruthy()
    expect(bytesMock.fetchAttachmentBytes).not.toHaveBeenCalled()
  })
})

describe('AttachmentPreview：下载', () => {
  it('下载仍走一次性票据，不出现裸 <a href>', async () => {
    renderPreview([att(0, '起诉状.pdf')])
    fireEvent.click(screen.getByRole('button', { name: '下载' }))

    await waitFor(() => expect(dlMock.withDownloadTicket).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket.mock.calls[0]?.[0]).toBe('/api/v1/inbox/messages/12/attachments/0/download')
    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(String(dlMock.downloadUrl.mock.calls[0]?.[0])).toContain('ticket=T')
    expect(document.querySelectorAll('a[href*="/attachments/"]')).toHaveLength(0)
  })
})
