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

const requestSaveMock = vi.hoisted(() => vi.fn(() => true))

vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (p: { fileUrl: string; fileName: string; mode?: string; onEditorReady?: (h: unknown) => void }) => {
    // 立即交出句柄，模拟「编辑器就绪」（另存为要点到 requestSave）
    p.onEditorReady?.({ requestSave: requestSaveMock })
    return (
      <div data-testid="office-view" data-url={p.fileUrl} data-mode={p.mode}>
        {p.fileName}
      </div>
    )
  },
}))

// 意图登记接口：另存为走它（不发文件字节，只登记「下次保存写成这个名字」）
const intentMock = vi.hoisted(() => vi.fn())
vi.mock('../../api', async (orig) => {
  const actual = await orig<typeof import('../../api')>()
  return { ...actual, registerFolderSaveAsIntent: intentMock }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

const ticketMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download-ticket', () => ({
  withDownloadTicket: (p: string) => ticketMock(p) as Promise<string>,
}))

import { toast } from 'sonner'

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
  requestSaveMock.mockReset()
  requestSaveMock.mockReturnValue(true)
  intentMock.mockReset()
  intentMock.mockImplementation((_kind: string, _id: number, subpath: string, name: string) =>
    Promise.resolve({ registered: true, name, subpath }),
  )
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
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

  it('docx 才给「另存为」', () => {
    setup()
    expect(screen.getByRole('button', { name: /另存为/ })).toBeTruthy()
  })

  it('案件文件夹的 docx 不给「另存为」（cases 没有 folder-save-as 系列端点）', () => {
    setup({ kind: 'case', ownerId: 399, file: { subpath: '2-诉状/起诉状.docx', name: '起诉状.docx' } })
    expect(screen.getByRole('button', { name: /保存/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /另存为/ })).toBeNull()
  })

  it('另存为：先登记意图（默认名字），再触发 DS 保存', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /另存为/ }))
    await waitFor(() => expect(requestSaveMock).toHaveBeenCalledTimes(1))
    const [kind, ownerId, subpath, name] = intentMock.mock.calls[0]!
    expect(kind).toBe('contract')
    expect(ownerId).toBe(318)
    // subpath 传已解码一次的原文（与 folderFileUrl 同一口径），不许多 encode
    expect(subpath).toBe('1-合同/a.docx')
    expect(name).toMatch(/^顾问合同\[修订版\]V1_\d{8}\.docx$/)
    expect(vi.mocked(toast.success)).toHaveBeenCalled()
  })

  it('另存为登记失败：报错且**不**触发保存（否则会把原稿原地覆盖）', async () => {
    intentMock.mockRejectedValueOnce(new Error('boom'))
    setup()
    fireEvent.click(screen.getByRole('button', { name: /另存为/ }))
    await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled())
    expect(requestSaveMock).not.toHaveBeenCalled()
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled()
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
