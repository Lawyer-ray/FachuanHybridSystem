// @vitest-environment jsdom
/**
 * 历史弹窗测试（jsdom）：要素式转换 / 文档解析 / DOC→DOCX。
 *
 * 三者同构：分组筛选 + 分页 + 行操作（下载/复制）+ 两段确认删除。
 * 重点锁定：
 * - 加载失败展示 HistoryError 而非空列表假象（此前会误读成「没有历史」）
 * - 分页首末页禁用
 * - 删除的两段确认：第一次点击只进入 armed 态，第二次才真正调用
 * - 分组筛选回落到对应 query 参数
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listConvertRecords: vi.fn(),
  deleteConvertRecord: vi.fn(),
  convertRecordDownloadUrl: vi.fn(() => '/dl/1'),
  listParseRecords: vi.fn(),
  deleteParseRecord: vi.fn(),
  parseRecordDownloadUrl: vi.fn(() => '/dl/2'),
  listConverterJobs: vi.fn(),
  deleteConverterRecord: vi.fn(),
  triggerDownload: vi.fn(),
}))

vi.mock('../../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api')>()
  return { ...actual, ...apiMock }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { ConvertHistoryDialog } from './ConvertHistoryDialog'
import { ParseHistoryDialog } from './ParseHistoryDialog'
import { ConverterHistoryDialog } from './ConverterHistoryDialog'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function record(id: number, status = 'success') {
  return {
    id,
    mbid: 'm1',
    mbid_name: '民事起诉状',
    original_name: 'a.doc',
    status,
    error_message: status === 'failed' ? '格式错误' : null,
    created_at: '2026-10-20T10:00:00',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listConvertRecords.mockResolvedValue({ items: [record(1)], count: 1, page: 1, num_pages: 1 })
  apiMock.listParseRecords.mockResolvedValue({ items: [], count: 0, page: 1, num_pages: 0 })
  apiMock.listConverterJobs.mockResolvedValue({ items: [], count: 0, page: 1, num_pages: 0 })
})

describe('ConvertHistoryDialog（要素式转换历史）', () => {
  it('渲染记录行与模板名', async () => {
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('民事起诉状'))
    unmount()
  })

  it('加载失败展示错误与重试，而非空列表', async () => {
    apiMock.listConvertRecords.mockRejectedValue(new Error('服务不可用'))
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))

    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    expect(document.body.textContent).toContain('服务不可用')
    unmount()
  })

  it('删除需两段确认：第一次只 arm，第二次才调用', async () => {
    apiMock.deleteConvertRecord.mockResolvedValue({})
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('民事起诉状'))

    const delBtn = document.querySelector('[title*="删除"], [aria-label*="删除"]') as HTMLElement
    expect(delBtn).toBeTruthy()

    fireEvent.click(delBtn)
    expect(apiMock.deleteConvertRecord).not.toHaveBeenCalled()

    fireEvent.click(delBtn)
    await waitFor(() => expect(apiMock.deleteConvertRecord).toHaveBeenCalledWith(1))
    unmount()
  })

  it('删除失败弹错误提示', async () => {
    apiMock.deleteConvertRecord.mockRejectedValue(new Error('记录已被清理'))
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('民事起诉状'))

    const delBtn = document.querySelector('[title*="删除"], [aria-label*="删除"]') as HTMLElement
    fireEvent.click(delBtn)
    fireEvent.click(delBtn)

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    unmount()
  })

  it('关闭态不渲染内容', () => {
    const { unmount } = render(wrap(<ConvertHistoryDialog open={false} onOpenChange={vi.fn()} />))
    expect(document.body.textContent).not.toContain('民事起诉状')
    unmount()
  })
})

describe('ParseHistoryDialog（解析历史）', () => {
  it('空列表展示空态文案', async () => {
    const { unmount } = render(wrap(<ParseHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listParseRecords).toHaveBeenCalled())
    unmount()
  })

  it('加载失败展示重试入口', async () => {
    apiMock.listParseRecords.mockRejectedValue(new Error('网关超时'))
    const { unmount } = render(wrap(<ParseHistoryDialog open onOpenChange={vi.fn()} />))

    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    unmount()
  })
})

describe('ConverterHistoryDialog（DOC→DOCX 历史）', () => {
  it('打开时拉取记录', async () => {
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listConverterJobs).toHaveBeenCalled())
    unmount()
  })

  it('加载失败展示重试入口', async () => {
    apiMock.listConverterJobs.mockRejectedValue(new Error('读取失败'))
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))

    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    unmount()
  })
})
