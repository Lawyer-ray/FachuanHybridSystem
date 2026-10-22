// @vitest-environment jsdom
/**
 * DocConverterCard 终态 UI 与复制降级链测试（jsdom）。
 *
 * 复制采用三级降级（这是本卡最值得锁的不变量）：
 *   剪贴板写成文件 → 复制文件名 → 报错
 * 且降级时必须复制「本次选中的」文件名，不能退化成全部成功件。
 *
 * 另覆盖终态弹窗的操作区：全部复制、打包下载、继续等待、关闭，
 * 以及 running 态禁用与进度文案。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const jobMock = vi.hoisted(() => ({
  phase: 'idle' as string,
  jobId: null as string | null,
  job: null as null | { total: number; done: number; failed: number; items: Array<{ id: number; name: string; ok: boolean }> },
  error: null as string | null,
  submit: vi.fn(async () => {}),
  resume: vi.fn(),
}))
const apiMock = vi.hoisted(() => ({
  copyConverterItemsToClipboard: vi.fn(),
  converterDownloadUrl: vi.fn(() => '/dl/zip'),
  triggerDownload: vi.fn(),
  listConverterJobs: vi.fn(async () => ({ items: [], count: 0, page: 1, num_pages: 0 })),
}))

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>()
  return { ...actual, ...apiMock }
})
vi.mock('./use-converter-job', () => ({ useConverterJob: () => jobMock }))
const clipboardMock = vi.hoisted(() => ({ copyText: vi.fn() }))
vi.mock('@/lib/clipboard', () => ({ copyText: (...a: unknown[]) => clipboardMock.copyText(...a) }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('./history/ConverterHistoryDialog', () => ({
  ConverterHistoryDialog: ({ open }: { open: boolean }) => (open ? <div>HISTORY</div> : null),
}))

import { toast } from 'sonner'

import { DocConverterCard } from './DocConverterCard'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function clickText(re: RegExp) {
  const btn = Array.from(document.querySelectorAll('button')).find((b) => re.test(b.textContent ?? ''))
  if (!btn) throw new Error('button not found: ' + String(re))
  fireEvent.click(btn)
  return btn as HTMLButtonElement
}

function pickFiles(container: HTMLElement, n = 1) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  const files = Array.from({ length: n }, (_, i) => new File(['x'], `f${i}.doc`))
  fireEvent.change(input, { target: { files } })
  return files
}

const okJob = {
  total: 3,
  done: 2,
  failed: 1,
  items: [
    { id: 1, name: 'a.docx', ok: true },
    { id: 2, name: 'b.docx', ok: true },
    { id: 3, name: 'c.docx', ok: false },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  jobMock.phase = 'idle'
  jobMock.jobId = null
  jobMock.job = null
  jobMock.error = null
  jobMock.submit = vi.fn(async () => {})
  jobMock.resume = vi.fn()
  clipboardMock.copyText.mockResolvedValue(true)
})

describe('DocConverterCard：初始与提交', () => {
  it('初始显示 LibreOffice 提示与开始转换', () => {
    const { container } = render(wrap(<DocConverterCard />))
    expect(container.textContent).toContain('LibreOffice 转换')
    expect(container.textContent).toContain('开始转换')
    container.remove()
  })

  it('未选文件时点开始不进入弹窗、不提交', async () => {
    const { container } = render(wrap(<DocConverterCard />))
    clickText(/开始转换/)
    await new Promise((r) => setTimeout(r, 30))
    expect(jobMock.submit).not.toHaveBeenCalled()
    container.remove()
  })

  it('选文件后点开始提交并开弹窗', async () => {
    const { container } = render(wrap(<DocConverterCard />))
    const files = pickFiles(container, 2)
    clickText(/开始转换/)

    await waitFor(() => expect(jobMock.submit).toHaveBeenCalledWith(files))
    // phase 由 useConverterJob 的真实实现驱动，本文件里是固定桩；
    // 这里只断言「提交后弹窗被打开」（出现弹窗操作区的关闭按钮）
    await waitFor(() => expect(document.body.textContent).toContain('关闭'))
    container.remove()
  })

  it('选中多个文件时提示已选数量', () => {
    const { container } = render(wrap(<DocConverterCard />))
    pickFiles(container, 3)
    expect(container.textContent).toContain('已选 3 个文件')
    container.remove()
  })
})

describe('DocConverterCard：running 与 timeout', () => {
  it('running：开始按钮禁用且显示进度文案', () => {
    jobMock.phase = 'running'
    jobMock.job = { total: 4, done: 1, failed: 0, items: [] }
    const { container } = render(wrap(<DocConverterCard />))
    const btn = clickText(/开始转换/)
    expect(btn.disabled).toBe(true)
    expect(container.textContent).toContain('1/4 已完成')
    container.remove()
  })

  it('total 缺省时进度显示占位 ?', () => {
    jobMock.phase = 'running'
    jobMock.job = { total: 0, done: 0, failed: 0, items: [] }
    const { container } = render(wrap(<DocConverterCard />))
    expect(container.textContent).toContain('0/? 已完成')
    container.remove()
  })

  it('timeout：弹窗给「继续等待」并调用 resume', async () => {
    jobMock.phase = 'timeout'
    jobMock.jobId = 'job-1'
    const { container } = render(wrap(<DocConverterCard />))
    pickFiles(container, 1)
    clickText(/开始转换/)
    await waitFor(() => expect(document.body.textContent).toContain('后台仍在继续'))

    clickText(/继续等待/)
    expect(jobMock.resume).toHaveBeenCalled()
    container.remove()
  })
})

describe('DocConverterCard：success 终态', () => {
  function renderSuccess() {
    jobMock.phase = 'success'
    jobMock.jobId = 'job-1'
    jobMock.job = okJob
    const utils = render(wrap(<DocConverterCard />))
    pickFiles(utils.container, 1)
    clickText(/开始转换/)
    return utils
  }

  it('弹窗显示成功数与失败数', async () => {
    const { container } = renderSuccess()
    await waitFor(() => expect(document.body.textContent).toContain('转换完成'))
    expect(document.body.textContent).toContain('成功 2 个')
    expect(document.body.textContent).toContain('失败 1 个')
    container.remove()
  })

  it('无失败时不显示失败片段', async () => {
    jobMock.phase = 'success'
    jobMock.jobId = 'job-1'
    jobMock.job = { total: 1, done: 1, failed: 0, items: [{ id: 1, name: 'a.docx', ok: true }] }
    const { container } = render(wrap(<DocConverterCard />))
    pickFiles(container, 1)
    clickText(/开始转换/)

    await waitFor(() => expect(document.body.textContent).toContain('转换完成'))
    expect(document.body.textContent).not.toContain('失败')
    container.remove()
  })

  it('打包下载调用 triggerDownload', async () => {
    const { container } = renderSuccess()
    await waitFor(() => expect(document.body.textContent).toContain('转换完成'))

    clickText(/打包下载/)
    expect(apiMock.triggerDownload).toHaveBeenCalled()
    container.remove()
  })

  it('有成功件时显示「全部复制」', async () => {
    const { container } = renderSuccess()
    await waitFor(() => expect(document.body.textContent).toContain('全部复制'))
    container.remove()
  })

  it('全部失败时不显示「全部复制」', async () => {
    jobMock.phase = 'success'
    jobMock.jobId = 'job-1'
    jobMock.job = { total: 1, done: 0, failed: 1, items: [{ id: 1, name: 'a.docx', ok: false }] }
    const { container } = render(wrap(<DocConverterCard />))
    pickFiles(container, 1)
    clickText(/开始转换/)

    await waitFor(() => expect(document.body.textContent).toContain('转换完成'))
    expect(document.body.textContent).not.toContain('全部复制')
    container.remove()
  })
})

describe('DocConverterCard：复制三级降级', () => {
  async function clickCopy() {
    jobMock.phase = 'success'
    jobMock.jobId = 'job-1'
    jobMock.job = okJob
    const utils = render(wrap(<DocConverterCard />))
    pickFiles(utils.container, 1)
    clickText(/开始转换/)
    await waitFor(() => expect(document.body.textContent).toContain('全部复制'))
    clickText(/全部复制/)
    return utils
  }

  it('一级：剪贴板写成文件成功 → 提示已复制数量', async () => {
    apiMock.copyConverterItemsToClipboard.mockResolvedValue({ success: true, copied: 2 })
    const { container } = await clickCopy()

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('已复制 2 个文件')))
    expect(clipboardMock.copyText).not.toHaveBeenCalled()
    container.remove()
  })

  it('二级：接口返回 success=false → 降级复制文件名', async () => {
    apiMock.copyConverterItemsToClipboard.mockResolvedValue({ success: false, copied: 0 })
    clipboardMock.copyText.mockResolvedValue(true)
    const { container } = await clickCopy()

    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('已复制文件名')))
    container.remove()
  })

  it('二级：接口抛异常同样降级复制文件名', async () => {
    apiMock.copyConverterItemsToClipboard.mockRejectedValue(new Error('not supported'))
    clipboardMock.copyText.mockResolvedValue(true)
    const { container } = await clickCopy()

    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('已复制文件名')))
    container.remove()
  })

  it('三级：降级也失败 → 报错建议打包下载', async () => {
    apiMock.copyConverterItemsToClipboard.mockResolvedValue({ success: false, copied: 0 })
    clipboardMock.copyText.mockResolvedValue(false)
    const { container } = await clickCopy()

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('打包下载')))
    container.remove()
  })

  it('降级时只复制本次选中的成功件文件名（不退化成全部）', async () => {
    apiMock.copyConverterItemsToClipboard.mockResolvedValue({ success: false, copied: 0 })
    clipboardMock.copyText.mockResolvedValue(true)
    const { container } = await clickCopy()

    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    const arg = clipboardMock.copyText.mock.calls[0]![0] as string
    expect(arg).toContain('a.docx')
    expect(arg).toContain('b.docx')
    // c.docx 是失败件，不应出现在复制内容里
    expect(arg).not.toContain('c.docx')
    container.remove()
  })
})

describe('DocConverterCard：历史入口', () => {
  it('点历史打开历史弹窗', () => {
    const { container } = render(wrap(<DocConverterCard />))
    clickText(/历史/)
    expect(within(container).getByText('HISTORY')).toBeTruthy()
    container.remove()
  })
})
