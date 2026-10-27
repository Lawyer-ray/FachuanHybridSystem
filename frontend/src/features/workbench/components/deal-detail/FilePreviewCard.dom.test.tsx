// @vitest-environment jsdom
/**
 * FilePreviewCard 测试（页内预览）。
 *
 * 解决的问题：点文件就整页跳走，代价太大——律师看合同常要对照右栏的期限、
 * 当事人、收费，整页离开或弹窗遮住都会让对照失效。这里做「不离开页面的看」，
 * 真要改才升级到整页编辑器。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
  const onReview = vi.fn()
  // 保存成功后组件会 invalidate 文件夹树缓存，测试里也要有 Provider
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <FilePreviewCard
        kind="contract"
        ownerId={318}
        file={{ subpath: '1-合同/a.docx', name: '顾问合同.docx', size: 882000, modified_at: '2026-05-12T00:00:00Z' }}
        onClose={onClose}
        onReview={onReview}
        {...over}
      />
    </QueryClientProvider>,
  )
  return { onClose, onReview }
}

beforeEach(() => {
  ticketMock.mockReset()
  ticketMock.mockResolvedValue('/x?ticket=t1')
})

describe('FilePreviewCard', () => {
  it('docx 走编辑态；pdf 等不可编辑格式仍只读', () => {
    setup()
    const view = screen.getByTestId('office-view')
    expect(view.getAttribute('data-mode')).toBe('edit')
    expect(view.getAttribute('data-url')).toBe(
      '/api/v1/contracts/318/folder-file?subpath=1-%E5%90%88%E5%90%8C%2Fa.docx',
    )
  })

  it('案件文件同样走 OnlyOffice（URL 落在 /cases/ 通道），AI 审查入口不给', () => {
    // 诉讼项目的文件主体在案件绑定文件夹：同一个预览卡，kind=case 时
    // 取文件/保存回写走案件通道（后端 OnlyOffice 域注册表按路径分发）。
    // AI 审查流水线只吃合同文件夹：调用方（DealDetailPage）不传 onReview。
    const { onReview } = setup({
      kind: 'case',
      ownerId: 399,
      file: { subpath: '2-诉状/起诉状.docx', name: '起诉状.docx' },
      onReview: undefined,
    })
    const view = screen.getByTestId('office-view')
    expect(view.getAttribute('data-mode')).toBe('edit')
    expect(view.getAttribute('data-url')).toBe(
      '/api/v1/cases/399/folder-file?subpath=2-%E8%AF%89%E7%8A%B6%2F%E8%B5%B7%E8%AF%89%E7%8A%B6.docx',
    )
    expect(screen.queryByRole('button', { name: /AI 审查/ })).toBeNull()
    expect(onReview).not.toHaveBeenCalled()
  })

  it('显示元信息（日期与大小）', () => {
    setup()
    expect(screen.getByText('2026-05-12')).toBeTruthy()
    expect(screen.getByText(/KB|MB/)).toBeTruthy()
  })

  it('docx 直接进编辑态（不再跳整页），并提供保存', () => {
    setup()
    expect(screen.getByTestId('office-view').getAttribute('data-mode')).toBe('edit')
    expect(screen.getByRole('button', { name: /保存/ })).toBeTruthy()
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
    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('非 docx 不给保存/另存为（改完存不回去，别给假按钮）', () => {
    setup({ file: { subpath: 'a.pdf', name: '发票.pdf' } })
    expect(screen.getByTestId('office-view').getAttribute('data-mode')).toBe('view')
    expect(screen.queryByRole('button', { name: /保存/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /另存为/ })).toBeNull()
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
