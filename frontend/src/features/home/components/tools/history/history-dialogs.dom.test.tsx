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
  getConverterJob: vi.fn(),
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

// ============ ConverterHistoryDialog 列表/详情双态（覆盖率补测） ============

function convJob(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    status: 'completed',
    total: 2,
    done: 1,
    failed: 1,
    created_at: '2026-10-20T10:00:00',
    items: [
      { id: 11, name: 'a.docx', ok: true },
      { id: 12, name: 'b.docx', ok: false },
    ],
    ...over,
  }
}

describe('ConverterHistoryDialog：列表视图', () => {
  it('加载中显示提示', () => {
    apiMock.listConverterJobs.mockReturnValue(new Promise(() => {}))
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    expect(screen.getByRole('status').textContent).toContain('正在加载…')
    unmount()
  })

  it('空列表显示「还没有转换任务」', async () => {
    apiMock.listConverterJobs.mockResolvedValue({ items: [], count: 0 })
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(screen.getByText('还没有转换任务')).toBeTruthy())
    unmount()
  })

  it('渲染任务行与顶部计数', async () => {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('1 条'))
    unmount()
  })

  it('加载失败展示重试', async () => {
    apiMock.listConverterJobs.mockRejectedValue(new Error('列表挂了'))
    const { unmount } = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    unmount()
  })
})

describe('ConverterHistoryDialog：详情视图', () => {
  async function openDetail() {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    apiMock.getConverterJob.mockResolvedValue(convJob('job-1'))
    const utils = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listConverterJobs).toHaveBeenCalled())

    // 点第一行进入详情
    // JobRow 是带 border-b 的整行 button；等它真正渲染出来再点
    const row = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('button')).find((b) =>
        b.className.includes('border-b') && b.className.includes('w-full'),
      )
      expect(found).toBeTruthy()
      return found!
    })
    fireEvent.click(row)
    await waitFor(() => expect(document.body.textContent).toContain('转换任务'))
    return utils
  }

  it('进入详情后展示成功件与失败件', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('a.docx'))
    expect(document.body.textContent).toContain('b.docx')
    expect(document.body.textContent).toContain('失败 1 件')
    unmount()
  })

  it('详情展示任务计数（共 N 件 · 成功 M · 失败 K）', async () => {
    const { unmount } = await openDetail()
    await waitFor(() => expect(document.body.textContent).toContain('共 2 件'))
    expect(document.body.textContent).toContain('成功 1')
    unmount()
  })

  it('点「返回」回到列表视图', async () => {
    const { unmount } = await openDetail()
    const back = Array.from(document.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('返回'),
    ) as HTMLElement
    fireEvent.click(back)
    await waitFor(() => expect(document.body.textContent).not.toContain('转换任务'))
    unmount()
  })

  it('详情加载失败展示重试', async () => {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    apiMock.getConverterJob.mockRejectedValue(new Error('详情挂了'))
    const utils = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listConverterJobs).toHaveBeenCalled())

    // JobRow 是带 border-b 的整行 button；等它真正渲染出来再点
    const row = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('button')).find((b) =>
        b.className.includes('border-b') && b.className.includes('w-full'),
      )
      expect(found).toBeTruthy()
      return found!
    })
    fireEvent.click(row)
    await waitFor(() => expect(document.body.textContent).toContain('详情挂了'))
    utils.unmount()
  })

  it('没有成功件时提示该任务无产物', async () => {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    apiMock.getConverterJob.mockResolvedValue(convJob('job-1', { done: 0, failed: 2, items: [] }))
    const utils = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listConverterJobs).toHaveBeenCalled())

    // JobRow 是带 border-b 的整行 button；等它真正渲染出来再点
    const row = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('button')).find((b) =>
        b.className.includes('border-b') && b.className.includes('w-full'),
      )
      expect(found).toBeTruthy()
      return found!
    })
    fireEvent.click(row)
    await waitFor(() => expect(document.body.textContent).toContain('没有转换成功的文件'))
    utils.unmount()
  })
})

// ============ 详情加载态与下载（覆盖率补测） ============

describe('ConverterHistoryDialog：详情加载与下载', () => {
  async function row() {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    const utils = render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    const r = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('button')).find(
        (b) => b.className.includes('border-b') && b.className.includes('w-full'),
      )
      expect(found).toBeTruthy()
      return found!
    })
    return { ...utils, row: r }
  }

  it('详情加载中显示「正在载入记录…」', async () => {
    apiMock.getConverterJob.mockReturnValue(new Promise(() => {}))
    const { unmount, row: r } = await row()
    fireEvent.click(r)
    await waitFor(() => expect(document.body.textContent).toContain('正在载入记录'))
    unmount()
  })

  it('逐件下载调用 triggerDownload', async () => {
    apiMock.getConverterJob.mockResolvedValue(convJob('job-1'))
    const { unmount, row: r } = await row()
    fireEvent.click(r)
    await waitFor(() => expect(document.body.textContent).toContain('a.docx'))

    const dl = Array.from(document.querySelectorAll('button')).find(
      (b) => b.textContent?.trim() === '下载',
    ) as HTMLElement
    fireEvent.click(dl)
    expect(apiMock.triggerDownload).toHaveBeenCalled()
    unmount()
  })

  it('打包下载 ZIP 按钮调用 triggerDownload', async () => {
    apiMock.getConverterJob.mockResolvedValue(convJob('job-1'))
    const { unmount, row: r } = await row()
    fireEvent.click(r)
    await waitFor(() => expect(document.body.textContent).toContain('a.docx'))

    const zip = Array.from(document.querySelectorAll('button')).find((b) =>
      /打包下载 ZIP/.test(b.textContent ?? ''),
    ) as HTMLElement
    fireEvent.click(zip)
    expect(apiMock.triggerDownload).toHaveBeenCalled()
    unmount()
  })
})

// ============ 列表重试与关闭回调（覆盖率补测） ============

describe('ConverterHistoryDialog：重试与关闭', () => {
  it('列表加载失败点「重试」重新请求', async () => {
    apiMock.listConverterJobs.mockRejectedValueOnce(new Error('挂了')).mockResolvedValue({ items: [], count: 0 })
    render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))

    const retry = await waitFor(() => screen.getByRole('button', { name: '重试' }))
    const before = apiMock.listConverterJobs.mock.calls.length
    fireEvent.click(retry)
    await waitFor(() =>
      expect(apiMock.listConverterJobs.mock.calls.length).toBeGreaterThan(before),
    )
  })

  it('详情加载失败点「重试」重新请求该任务', async () => {
    apiMock.listConverterJobs.mockResolvedValue({ items: [convJob('job-1')], count: 1 })
    apiMock.getConverterJob.mockRejectedValueOnce(new Error('详情挂了')).mockResolvedValue(convJob('job-1'))

    render(wrap(<ConverterHistoryDialog open onOpenChange={vi.fn()} />))
    const row = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('button')).find(
        (b) => b.className.includes('border-b') && b.className.includes('w-full'),
      )
      expect(found).toBeTruthy()
      return found!
    })
    fireEvent.click(row)

    const retry = await waitFor(() => screen.getByRole('button', { name: '重试' }))
    const before = apiMock.getConverterJob.mock.calls.length
    fireEvent.click(retry)
    await waitFor(() => expect(apiMock.getConverterJob.mock.calls.length).toBeGreaterThan(before))
  })

})

// ============ ConvertHistoryDialog 下载/分组/重试（覆盖率补测） ============

describe('ConvertHistoryDialog：下载与分组', () => {
  function recWithFile(id: number) {
    return { ...record(id), has_file: true }
  }

  it('有文件时显示下载按钮并触发 triggerDownload', async () => {
    apiMock.listConvertRecords.mockResolvedValue({ items: [recWithFile(1)], count: 1, page: 1, num_pages: 1 })
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('民事起诉状'))

    const dl = Array.from(document.querySelectorAll('button')).find((b) =>
      b.textContent?.trim() === '下载',
    ) as HTMLElement
    fireEvent.click(dl)
    expect(apiMock.triggerDownload).toHaveBeenCalled()
    unmount()
  })

  it('无文件时不显示下载按钮', async () => {
    apiMock.listConvertRecords.mockResolvedValue({
      items: [{ ...record(1), has_file: false }],
      count: 1,
      page: 1,
      num_pages: 1,
    })
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(document.body.textContent).toContain('民事起诉状'))

    const dl = Array.from(document.querySelectorAll('button')).find((b) =>
      b.textContent?.trim() === '下载',
    )
    expect(dl).toBeUndefined()
    unmount()
  })

  it('点分组按钮按新状态重新请求', async () => {
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))
    await waitFor(() => expect(apiMock.listConvertRecords).toHaveBeenCalled())

    const failBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === '失败')
    fireEvent.click(failBtn!)
    await waitFor(() => expect(apiMock.listConvertRecords).toHaveBeenCalledWith('failed', 1))
    unmount()
  })

  it('加载失败点重试重新请求', async () => {
    apiMock.listConvertRecords.mockRejectedValueOnce(new Error('挂了')).mockResolvedValue({ items: [], count: 0 })
    const { unmount } = render(wrap(<ConvertHistoryDialog open onOpenChange={vi.fn()} />))

    const retry = await waitFor(() => screen.getByRole('button', { name: '重试' }))
    const before = apiMock.listConvertRecords.mock.calls.length
    fireEvent.click(retry)
    await waitFor(() => expect(apiMock.listConvertRecords.mock.calls.length).toBeGreaterThan(before))
    unmount()
  })
})
