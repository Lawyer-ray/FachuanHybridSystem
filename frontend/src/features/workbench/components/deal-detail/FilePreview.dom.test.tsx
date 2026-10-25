// @vitest-environment jsdom
/**
 * FilePreview 测试（jsdom）。
 *
 * 这修的是「点 docx 只会下载」+「预览改不了」：
 * 浏览器没有 docx 渲染器，`window.open(下载地址)` 对 .docx 必然落盘。
 *
 * 现在点行 = 就地 OnlyOffice，并且：
 * - 「保存」覆盖原文件，带 mtime 乐观锁；
 * - 「另存为」默认 `原名[修订版]V1_<今天>.docx`，不动原文件；
 * - 「AI 审查」只在 docx 出现（流水线只吃 docx）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (p: {
    fileUrl: string
    fileName: string
    mode?: string
    onEditorReady?: (h: unknown) => void
  }) => {
    // 立即交出句柄，模拟「编辑器就绪」
    p.onEditorReady?.({ getDocxBlob: () => Promise.resolve(new Blob(['docx-bytes'])) })
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

const saveMock = vi.hoisted(() => vi.fn())
const saveAsMock = vi.hoisted(() => vi.fn())
vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>()
  return {
    ...actual,
    saveFolderFile: (...a: unknown[]) => saveMock(...a) as Promise<unknown>,
    saveFolderFileAs: (...a: unknown[]) => saveAsMock(...a) as Promise<unknown>,
  }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

import { FilePreview } from './FilePreview'
import { defaultSaveAsName } from './save-as-name'

function setup(over: Partial<Parameters<typeof FilePreview>[0]> = {}) {
  const onBack = vi.fn()
  const onReview = vi.fn()
  const onSaved = vi.fn()
  render(
    <FilePreview
      kind="contract"
      ownerId={318}
      file={{ subpath: '1-合同/a.docx', name: '顾问合同.docx', mtime: 1700000000 }}
      onBack={onBack}
      onReview={onReview}
      onSaved={onSaved}
      {...over}
    />,
  )
  return { onBack, onReview, onSaved }
}

beforeEach(() => {
  ticketMock.mockReset()
  saveMock.mockReset()
  saveAsMock.mockReset()
  ticketMock.mockResolvedValue('/x?ticket=t1')
  saveMock.mockResolvedValue({ subpath: '1-合同/a.docx', name: '顾问合同.docx', size: 10 })
  saveAsMock.mockResolvedValue({ subpath: '1-合同/b.docx', name: 'b.docx', size: 10 })
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

  it('非 docx 只读，且不给保存/另存为/AI 审查', () => {
    setup({ file: { subpath: 'a.pdf', name: '发票.pdf' } })
    expect(screen.getByTestId('office-view').getAttribute('data-mode')).toBe('view')
    expect(screen.queryByRole('button', { name: /保存/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /另存为/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /AI 审查/ })).toBeNull()
  })

  it('保存：覆盖原文件并带上打开时的 mtime（乐观锁）', async () => {
    const { onSaved } = setup()
    fireEvent.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(saveMock).toHaveBeenCalled())
    const [kind, ownerId, subpath, blob, mtime] = saveMock.mock.calls[0] ?? []
    expect(kind).toBe('contract')
    expect(ownerId).toBe(318)
    expect(subpath).toBe('1-合同/a.docx')
    expect(blob).toBeInstanceOf(Blob)
    // mtime 必须传：两人同开时靠它防静默覆盖
    expect(mtime).toBe(1700000000)
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('另存为：默认名带 [修订版]V1 与今天日期，且不动原文件', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('顾问合同[修订版]V1_20261025.docx')
    const { onSaved } = setup()

    fireEvent.click(screen.getByRole('button', { name: /另存为/ }))

    await waitFor(() => expect(saveAsMock).toHaveBeenCalled())
    const [kind, ownerId, subpath, name] = saveAsMock.mock.calls[0] ?? []
    expect(kind).toBe('contract')
    expect(ownerId).toBe(318)
    // subpath 指向源文件（后端据它定位目录），不是新名字
    expect(subpath).toBe('1-合同/a.docx')
    expect(name).toBe('顾问合同[修订版]V1_20261025.docx')

    // 默认值也要符合约定
    expect(promptSpy).toHaveBeenCalledWith(expect.any(String), defaultSaveAsName('顾问合同.docx'))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    promptSpy.mockRestore()
  })

  it('另存为取消时不发请求', () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null)
    setup()
    fireEvent.click(screen.getByRole('button', { name: /另存为/ }))
    expect(saveAsMock).not.toHaveBeenCalled()
    promptSpy.mockRestore()
  })

  it('⌘S 触发保存（律师的肌肉记忆）', async () => {
    setup()
    fireEvent.keyDown(document, { key: 's', metaKey: true })
    await waitFor(() => expect(saveMock).toHaveBeenCalled())
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
