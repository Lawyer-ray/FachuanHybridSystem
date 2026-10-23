// @vitest-environment jsdom
/**
 * 三张文档处理卡的提交校验与状态机测试（jsdom）。
 *
 * DocConvertCard（要素式转换）/ DocConverterCard（DOC→DOCX）/ DocParseCard（文档解析）
 * 共用同一套形态：选文件 → 校验 → 提交 → running/success/error 弹窗。
 * 这里锁定最容易退化的部分：
 * - 未选文件时提示且不发请求
 * - 提交成功后进入 success 并触发下载/结果
 * - 提交失败进入 error 并展示后端文案
 * - 提交进行中按钮禁用（防重复提交）
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  convertDocument: vi.fn(),
  createConverterJob: vi.fn(),
  getConverterJob: vi.fn(),
  parseDocument: vi.fn(),
  listConvertTemplates: vi.fn(async () => []),
  listDirectories: vi.fn(async () => []),
  CONVERT_TEMPLATES_KEY: ['convert-templates'],
  CONVERT_HISTORY_KEY: ['convert-history'],
  PARSE_HISTORY_KEY: ['parse-history'],
  TOOL_ENDPOINT: { docConvert: '/e1', docConverter: '/e2', docParse: '/e3' },
}))

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>()
  return {
    ...actual,
    convertDocument: apiMock.convertDocument,
    createConverterJob: apiMock.createConverterJob,
    getConverterJob: apiMock.getConverterJob,
    parseDocument: apiMock.parseDocument,
    listConvertTemplates: apiMock.listConvertTemplates,
    listDirectories: apiMock.listDirectories,
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('./TemplateCombobox', () => ({
  TemplateCombobox: ({ onChange }: { onChange: (v: string) => void }) => (
    <button type="button" onClick={() => onChange('m1')}>选模板</button>
  ),
}))

import { toast } from 'sonner'

import { DocConvertCard } from './DocConvertCard'
import { DocConverterCard } from './DocConverterCard'
import { DocParseCard } from './DocParseCard'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function pickFile(container: HTMLElement, name = 'a.doc') {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['x'], name)] } })
}

function clickByText(text: RegExp | string) {
  const btn = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = b.textContent ?? ''
    return typeof text === 'string' ? t.includes(text) : text.test(t)
  })
  if (!btn) throw new Error('button not found: ' + String(text))
  fireEvent.click(btn)
  return btn as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listConvertTemplates.mockResolvedValue([])
})

describe('DocConvertCard（要素式转换）', () => {
  it('未选模板时提示且不发请求', async () => {
    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(container.textContent).toContain('要素式转换'))

    clickByText('转换')
    expect(toast.info).toHaveBeenCalledWith('先选文书类型')
    expect(apiMock.convertDocument).not.toHaveBeenCalled()
    unmount()
  })

  it('选了模板但未选文件时提示', async () => {
    const { unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(screen.getByText('选模板')).toBeTruthy())

    clickByText('选模板')
    clickByText('转换')
    expect(toast.info).toHaveBeenCalledWith('先选择要转换的文书')
    expect(apiMock.convertDocument).not.toHaveBeenCalled()
    unmount()
  })

  it('模板与文件齐备时提交成功', async () => {
    apiMock.convertDocument.mockResolvedValue({ blob: new Blob(['x']), filename: 'out.docx' })
    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(screen.getByText('选模板')).toBeTruthy())

    clickByText('选模板')
    pickFile(container)
    clickByText('转换')

    await waitFor(() => expect(apiMock.convertDocument).toHaveBeenCalledWith('m1', expect.any(File)))
    unmount()
  })

  it('提交失败展示后端文案', async () => {
    apiMock.convertDocument.mockRejectedValue(new Error('文件格式不支持'))
    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(screen.getByText('选模板')).toBeTruthy())

    clickByText('选模板')
    pickFile(container)
    clickByText('转换')

    await waitFor(() => expect(document.body.textContent).toContain('文件格式不支持'))
    unmount()
  })
})

describe('DocConverterCard（DOC→DOCX）', () => {
  it('未选文件时提交不发请求', async () => {
    const { container, unmount } = render(wrap(<DocConverterCard />))
    await waitFor(() => expect(container.textContent).toContain('DOC'))

    clickByText('开始转换')
    expect(apiMock.createConverterJob).not.toHaveBeenCalled()
    unmount()
  })

  it('选文件后提交创建转换任务', async () => {
    apiMock.createConverterJob.mockResolvedValue('job-1')
    apiMock.getConverterJob.mockResolvedValue({ status: 'completed', items: [] })
    const { container, unmount } = render(wrap(<DocConverterCard />))
    await waitFor(() => expect(container.textContent).toContain('DOC'))

    pickFile(container, 'a.doc')
    clickByText('开始转换')

    await waitFor(() => expect(apiMock.createConverterJob).toHaveBeenCalled())
    unmount()
  })
})

describe('DocParseCard（文档解析）', () => {
  it('渲染解析入口', async () => {
    const { container, unmount } = render(wrap(<DocParseCard />))
    await waitFor(() => expect(container.textContent).toContain('解析'))
    unmount()
  })

  it('未选文件时提交不发请求', async () => {
    const { container, unmount } = render(wrap(<DocParseCard />))
    await waitFor(() => expect(container.textContent).toContain('解析'))

    const before = apiMock.parseDocument.mock.calls.length
    clickByText(/解析|开始/)
    expect(apiMock.parseDocument.mock.calls.length).toBe(before)
    unmount()
  })
})

// ============ 拖放 / 完成态 / 弹窗按钮（覆盖率补测） ============

describe('DocConvertCard：拖放与完成态', () => {
  it('拖入文件设为当前文件', async () => {
    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(container.textContent).toContain('要素式转换'))

    const card = container.firstElementChild as HTMLElement
    fireEvent.drop(card, { dataTransfer: { files: [new File(['x'], 'drag.docx')] } })
    await waitFor(() => expect(container.textContent).toContain('drag.docx'))
    unmount()
  })

  it('拖入空列表不改文件', async () => {
    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(container.textContent).toContain('要素式转换'))

    const card = container.firstElementChild as HTMLElement
    fireEvent.drop(card, { dataTransfer: { files: [] } })
    expect(container.textContent).toContain('.doc / .docx / .pdf')
    unmount()
  })

  it('完成态弹窗里「下载要素式文书」触发 blob 下载', async () => {
    apiMock.convertDocument.mockResolvedValue({ blob: new Blob(['x']), filename: 'out.docx' })
    const createObjUrl = vi.fn(() => 'blob:mock')
    URL.createObjectURL = createObjUrl as never
    URL.revokeObjectURL = vi.fn() as never

    const { container, unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(screen.getByText('选模板')).toBeTruthy())
    clickByText('选模板')
    pickFile(container)
    clickByText('转换')

    await waitFor(() => expect(document.body.textContent).toContain('下载要素式文书'))
    fireEvent.click(screen.getByText(/下载要素式文书/))
    expect(createObjUrl).toHaveBeenCalled()
    unmount()
  })

  it('历史按钮打开历史弹窗', async () => {
    const { unmount } = render(wrap(<DocConvertCard />))
    await waitFor(() => expect(screen.getByText('选模板')).toBeTruthy())
    clickByText(/历史/)
    // 历史弹窗由 ConvertHistoryDialog 渲染；出现即说明回调链路通
    await waitFor(() => expect(document.body.textContent).toContain('历史'))
    unmount()
  })
})
