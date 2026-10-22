// @vitest-environment jsdom
/**
 * ParseHistoryDialog 测试（jsdom）。
 *
 * 同一弹窗内「列表 ⇄ 详情」切换（不叠第二层弹窗）：
 * - 列表：加载中/错误+重试/空态/行渲染（状态徽章、文件名、预览、后端、时间）
 * - 分组筛选（全部/已完成/失败）与切组重置页码
 * - 点某条进详情：文件名、状态、正文或错误、复制/下载按钮
 * - 详情加载中/失败、返回按钮回列表
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listParseRecords: vi.fn(),
  getParseRecord: vi.fn(),
}))
const outcomeMock = vi.hoisted(() => ({ copyOutcome: vi.fn(), downloadOutcome: vi.fn() }))

vi.mock('../../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api')>()
  return { ...actual, listParseRecords: apiMock.listParseRecords, getParseRecord: apiMock.getParseRecord }
})
vi.mock('../doc-parse-outcome', () => outcomeMock)
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { ParseHistoryDialog } from './ParseHistoryDialog'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function rec(id: number, over: Record<string, unknown> = {}) {
  return {
    id,
    status: 'completed',
    file_name: `doc${id}.pdf`,
    text_preview: `预览 ${id}`,
    error_message: null,
    backend_used: 'mineru',
    created_at: '2026-10-20T10:00:00',
    ...over,
  }
}

function detailRec(id: number, over: Record<string, unknown> = {}) {
  return {
    id,
    status: 'completed',
    file_name: `doc${id}.pdf`,
    markdown: '# 标题',
    text: '纯文本',
    error_message: null,
    backend_used: 'mineru',
    created_at: '2026-10-20T10:00:00',
    metadata: { page_count: 2 },
    ...over,
  }
}

function renderDialog(props: Partial<Parameters<typeof ParseHistoryDialog>[0]> = {}) {
  const onOpenChange = vi.fn()
  const utils = render(wrap(<ParseHistoryDialog open onOpenChange={onOpenChange} {...props} />))
  return { ...utils, onOpenChange }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listParseRecords.mockResolvedValue({ items: [rec(1)], count: 1 })
  apiMock.getParseRecord.mockResolvedValue(detailRec(1))
})

describe('ParseHistoryDialog：列表三态', () => {
  it('open=false 不请求', () => {
    const { unmount } = renderDialog({ open: false })
    expect(apiMock.listParseRecords).not.toHaveBeenCalled()
    unmount()
  })

  it('加载中显示提示', () => {
    apiMock.listParseRecords.mockReturnValue(new Promise(() => {}))
    const { unmount } = renderDialog()
    expect(screen.getByText('正在加载…')).toBeTruthy()
    unmount()
  })

  it('空列表显示空态', async () => {
    apiMock.listParseRecords.mockResolvedValue({ items: [], count: 0 })
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('这个筛选下没有记录')).toBeTruthy())
    unmount()
  })

  it('加载失败显示错误与重试', async () => {
    apiMock.listParseRecords.mockRejectedValue(new Error('网关超时'))
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText(/网关超时/)).toBeTruthy())
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    unmount()
  })
})

describe('ParseHistoryDialog：行渲染', () => {
  it('渲染文件名、预览、状态徽章、后端与时间', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('doc1.pdf')).toBeTruthy())

    const text = document.body.textContent ?? ''
    expect(text).toContain('预览 1')
    expect(text).toContain('已完成')
    expect(text).toContain('mineru')
    expect(text).toContain('10-20')
    unmount()
  })

  it('失败记录无预览时回退显示错误信息', async () => {
    apiMock.listParseRecords.mockResolvedValue({
      items: [rec(2, { status: 'failed', text_preview: '', error_message: '引擎超时' })],
      count: 1,
    })
    const { unmount } = renderDialog()
    await waitFor(() => expect(document.body.textContent).toContain('引擎超时'))
    unmount()
  })

  it('失败记录且无错误信息时回退「解析失败」', async () => {
    apiMock.listParseRecords.mockResolvedValue({
      items: [rec(3, { status: 'failed', text_preview: '', error_message: null })],
      count: 1,
    })
    const { unmount } = renderDialog()
    await waitFor(() => expect(document.body.textContent).toContain('解析失败'))
    unmount()
  })

  it('既无预览也无错误时显示「（无预览）」', async () => {
    apiMock.listParseRecords.mockResolvedValue({
      items: [rec(4, { status: 'processing', text_preview: null })],
      count: 1,
    })
    const { unmount } = renderDialog()
    await waitFor(() => expect(document.body.textContent).toContain('（无预览）'))
    unmount()
  })

  it('created_at 为 null 时不渲染时间（避免 Invalid Date）', async () => {
    apiMock.listParseRecords.mockResolvedValue({ items: [rec(5, { created_at: null })], count: 1 })
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('doc5.pdf')).toBeTruthy())
    expect(document.body.textContent).not.toContain('Invalid Date')
    unmount()
  })
})

describe('ParseHistoryDialog：分组与分页', () => {
  it('三个分组按钮都在，点「失败」带 status 重新请求', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('doc1.pdf')).toBeTruthy())

    const failBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === '失败')
    fireEvent.click(failBtn!)

    await waitFor(() => expect(apiMock.listParseRecords).toHaveBeenCalledWith('failed', 1))
    unmount()
  })

  it('点「全部」传 undefined 而非空串', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('doc1.pdf')).toBeTruthy())

    const allBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === '全部')
    fireEvent.click(allBtn!)
    await waitFor(() => expect(apiMock.listParseRecords).toHaveBeenCalledWith(undefined, 1))
    unmount()
  })
})

describe('ParseHistoryDialog：详情视图', () => {
  async function openDetail() {
    const utils = renderDialog()
    const row = await waitFor(() => screen.getByText('doc1.pdf').closest('button') as HTMLElement)
    fireEvent.click(row)
    await waitFor(() => expect(apiMock.getParseRecord).toHaveBeenCalledWith(1))
    return utils
  }

  it('进入详情展示正文', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('# 标题'))
    unmount()
  })

  it('成功记录显示复制与下载按钮', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(screen.getByRole('button', { name: /复制全文/ })).toBeTruthy())
    expect(screen.getByRole('button', { name: /下载 .md/ })).toBeTruthy()
    unmount()
  })

  it('点复制调用 copyOutcome', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(screen.getByRole('button', { name: /复制全文/ })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /复制全文/ }))
    expect(outcomeMock.copyOutcome).toHaveBeenCalled()
    unmount()
  })

  it('点下载调用 downloadOutcome 并带 basename', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(screen.getByRole('button', { name: /下载/ })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /下载 .md/ }))
    expect(outcomeMock.downloadOutcome).toHaveBeenCalledWith(expect.anything(), 'doc1')
    unmount()
  })

  it('无 markdown 时下载按钮文案为 .txt', async () => {
    apiMock.getParseRecord.mockResolvedValue(detailRec(1, { markdown: null }))
    const { unmount } = await openDetail()
    await waitFor(() => expect(screen.getByRole('button', { name: /下载 .txt/ })).toBeTruthy())
    unmount()
  })

  it('失败记录显示错误提示且无复制/下载', async () => {
    apiMock.getParseRecord.mockResolvedValue(
      detailRec(1, { status: 'failed', error_message: '引擎崩溃', markdown: null }),
    )
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('引擎崩溃'))
    expect(screen.queryByRole('button', { name: /复制全文/ })).toBeNull()
    unmount()
  })

  it('失败记录且无 error_message 时回退「该次解析失败」', async () => {
    apiMock.getParseRecord.mockResolvedValue(
      detailRec(1, { status: 'failed', error_message: null, markdown: null }),
    )
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('该次解析失败'))
    unmount()
  })

  it('点「返回」回到列表视图', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('# 标题'))

    const back = screen.getByRole('button', { name: /返回/ })
    fireEvent.click(back)
    await waitFor(() => expect(screen.getByText('doc1.pdf')).toBeTruthy())
    unmount()
  })

  it('详情加载失败显示重试', async () => {
    apiMock.getParseRecord.mockRejectedValue(new Error('详情挂了'))
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('详情挂了'))
    unmount()
  })

  it('解析结果为空时显示占位文案', async () => {
    apiMock.getParseRecord.mockResolvedValue(detailRec(1, { markdown: '', text: '' }))
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('（解析结果为空）'))
    unmount()
  })
})
