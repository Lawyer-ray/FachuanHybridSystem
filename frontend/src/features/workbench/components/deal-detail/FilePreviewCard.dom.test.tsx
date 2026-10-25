// @vitest-environment jsdom
/**
 * FilePreviewCard 测试（页内预览）。
 *
 * 解决的问题：点文件就整页跳走，代价太大——律师看合同常要对照右栏的期限、
 * 当事人、收费，整页离开或弹窗遮住都会让对照失效。这里做「不离开页面的看」，
 * 真要改才升级到整页编辑器。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (p: { fileUrl: string; fileName: string; mode?: string }) => (
    <div data-testid="office-view" data-url={p.fileUrl} data-mode={p.mode}>
      {p.fileName}
    </div>
  ),
}))

const ticketMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download-ticket', () => ({
  withDownloadTicket: (p: string) => ticketMock(p) as Promise<string>,
}))

import { FilePreviewCard } from './FilePreviewCard'

function setup(over: Partial<Parameters<typeof FilePreviewCard>[0]> = {}) {
  const onClose = vi.fn()
  const onOpenEditor = vi.fn()
  const onReview = vi.fn()
  render(
    <FilePreviewCard
      kind="contract"
      ownerId={318}
      file={{ subpath: '1-合同/a.docx', name: '顾问合同.docx', size: 882000, modified_at: '2026-05-12T00:00:00Z' }}
      onClose={onClose}
      onOpenEditor={onOpenEditor}
      onReview={onReview}
      {...over}
    />,
  )
  return { onClose, onOpenEditor, onReview }
}

beforeEach(() => {
  ticketMock.mockReset()
  ticketMock.mockResolvedValue('/x?ticket=t1')
})

describe('FilePreviewCard', () => {
  it('页内渲染只读画布（不改文档，改动走整页编辑器）', () => {
    setup()
    const view = screen.getByTestId('office-view')
    expect(view.getAttribute('data-mode')).toBe('view')
    expect(view.getAttribute('data-url')).toBe(
      '/api/v1/contracts/318/folder-file?subpath=1-%E5%90%88%E5%90%8C%2Fa.docx',
    )
  })

  it('显示元信息（日期与大小）', () => {
    setup()
    expect(screen.getByText('2026-05-12')).toBeTruthy()
    expect(screen.getByText(/KB|MB/)).toBeTruthy()
  })

  it('「打开编辑器」升级到整页', () => {
    const { onOpenEditor } = setup()
    fireEvent.click(screen.getByRole('button', { name: /打开编辑器/ }))
    expect(onOpenEditor).toHaveBeenCalledWith({ subpath: '1-合同/a.docx', name: '顾问合同.docx' })
  })

  it('docx 才有「AI 审查」', () => {
    const { onReview } = setup()
    fireEvent.click(screen.getByRole('button', { name: /AI 审查/ }))
    expect(onReview).toHaveBeenCalledWith({ subpath: '1-合同/a.docx', name: '顾问合同.docx' })
  })

  it('非 docx 不给「AI 审查」（流水线只吃 docx）', () => {
    setup({ file: { subpath: 'a.pdf', name: '发票.pdf' } })
    expect(screen.queryByRole('button', { name: /AI 审查/ })).toBeNull()
  })

  it('收起按钮回调 onClose', () => {
    const { onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: '收起预览' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('下载时现换一次性票据', async () => {
    const clickSpy = vi.fn()
    const orig = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = orig(tag)
      if (tag === 'a') el.click = clickSpy
      return el
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: /下载/ }))
    await waitFor(() => expect(clickSpy).toHaveBeenCalled())
    expect(ticketMock).toHaveBeenCalledTimes(1)
    vi.restoreAllMocks()
  })
})
