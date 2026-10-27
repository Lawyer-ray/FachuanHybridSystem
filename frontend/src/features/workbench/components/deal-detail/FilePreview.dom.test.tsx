// @vitest-environment jsdom
/**
 * FilePreview 测试（jsdom）。
 *
 * 这修的是「点 docx 只会下载」+「预览改不了」：
 * 浏览器没有 docx 渲染器，`window.open(下载地址)` 对 .docx 必然落盘。
 *
 * 现在点行 = 就地 OnlyOffice，并且：
 * - 「保存」原地覆盖原文件（DS forcesave 回调落盘，不做 mtime 校验）；
 * - 「另存为」先登记一次性意图再 forcesave，默认 `原名[修订版]V1_<今天>.docx`，
 *   原文件不动；只对合同文件夹的 docx 开放；
 * - 「AI 审查」只在 docx 出现（流水线只吃 docx）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (p: {
    fileUrl: string
    fileName: string
    mode?: string
    onEditorReady?: (h: unknown) => void
  }) => {
    // 立即交出句柄，模拟「编辑器就绪」
    p.onEditorReady?.({ requestSave: requestSaveMock })
    return (
      <div data-testid="office-view" data-url={p.fileUrl} data-mode={p.mode}>
        {p.fileName}
      </div>
    )
  },
}))

const ticketMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download-ticket', () => ({
  withDownloadTicket: (p: string) => ticketMock(p) as Promise<string>,
}))

const requestSaveMock = vi.hoisted(() => vi.fn(() => true))

// 意图登记接口：另存为走它（不发文件字节，只登记「下次保存写成这个名字」）
const intentMock = vi.hoisted(() => vi.fn())
vi.mock('../../api', async (orig) => {
  const actual = await orig<typeof import('../../api')>()
  return { ...actual, registerFolderSaveAsIntent: intentMock }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

import { toast } from 'sonner'

import { FilePreview } from './FilePreview'
import { defaultSaveAsName } from './save-as-name'

function setup(over: Partial<Parameters<typeof FilePreview>[0]> = {}) {
  const onBack = vi.fn()
  const onReview = vi.fn()
  const onSaved = vi.fn()
  // 保存成功后组件会 invalidate 文件夹树缓存，测试里也要有 Provider
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <FilePreview
        kind="contract"
        ownerId={318}
        file={{ subpath: '1-合同/a.docx', name: '顾问合同.docx', mtime: 1700000000 }}
        onBack={onBack}
        onReview={onReview}
        onSaved={onSaved}
        {...over}
      />
    </QueryClientProvider>,
  )
  return { onBack, onReview, onSaved }
}

beforeEach(() => {
  ticketMock.mockReset()
  requestSaveMock.mockReset()
  requestSaveMock.mockReturnValue(true)
  ticketMock.mockResolvedValue('/x?ticket=t1')
  intentMock.mockReset()
  intentMock.mockImplementation((_kind: string, _id: number, subpath: string, name: string) =>
    Promise.resolve({ registered: true, name, subpath }),
  )
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('FilePreview', () => {
  it('docx 用可编辑模式渲染', () => {
    setup()
    const view = screen.getByTestId('office-view')
    expect(view.getAttribute('data-mode')).toBe('edit')
    expect(view.getAttribute('data-url')).toBe(
      '/api/v1/contracts/318/folder-file?subpath=1-%E5%90%88%E5%90%8C%2Fa.docx',
    )
  })

  it('非 docx 只读，且不给保存/另存为/AI 审查（改完存不回去，别给假按钮）', () => {
    setup({ file: { subpath: 'a.pdf', name: '发票.pdf' } })
    expect(screen.getByTestId('office-view').getAttribute('data-mode')).toBe('view')
    expect(screen.queryByRole('button', { name: /保存/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /另存为/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /AI 审查/ })).toBeNull()
  })

  it('docx 才给「另存为」（与保存同在 docx 分支）', () => {
    setup()
    expect(screen.getByRole('button', { name: /另存为/ })).toBeTruthy()
  })

  it('案件文件夹的 docx 不给「另存为」（cases 没有 folder-save-as 系列端点）', () => {
    setup({ kind: 'case', ownerId: 399, file: { subpath: '2-诉状/起诉状.docx', name: '起诉状.docx' } })
    // 保存仍给：案件文件夹的原地保存走 cases 通道，后端有对应回调落盘
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

  it('保存：走 DS forcesave（不取字节自己上传）', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /保存/ }))
    // 落盘发生在 DS 回调里，页面只负责触发与延迟刷新
    expect(requestSaveMock).toHaveBeenCalled()
  })

  it('⌘S 触发保存（律师的肌肉记忆）', () => {
    setup()
    fireEvent.keyDown(document, { key: 's', metaKey: true })
    expect(requestSaveMock).toHaveBeenCalled()
  })

  it('返回按钮与 Esc 都回调 onBack', () => {
    const { onBack } = setup()
    fireEvent.click(screen.getByRole('button', { name: /合同文件夹/ }))
    expect(onBack).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onBack).toHaveBeenCalledTimes(2)
  })

  it('docx 显示 AI 审查并可触发', () => {
    const { onReview } = setup()
    fireEvent.click(screen.getByRole('button', { name: /AI 审查/ }))
    expect(onReview).toHaveBeenCalledWith({ subpath: '1-合同/a.docx', name: '顾问合同.docx' })
  })
})

describe('defaultSaveAsName', () => {
  it('拼出 原名[修订版]V1_日期', () => {
    expect(defaultSaveAsName('顾问合同.docx', new Date(2026, 9, 25))).toBe('顾问合同[修订版]V1_20261025.docx')
  })

  it('已带 [修订版] 的不重复叠加', () => {
    expect(defaultSaveAsName('顾问合同[修订版]V1_20260101.docx', new Date(2026, 9, 25))).toBe(
      '顾问合同[修订版]V1_20261025.docx',
    )
  })

  it('保留原扩展名', () => {
    expect(defaultSaveAsName('a.PDF', new Date(2026, 0, 5))).toBe('a[修订版]V1_20260105.PDF')
  })
})
