// @vitest-environment jsdom
/**
 * CourtSmsHistoryDialog 测试（jsdom）。
 *
 * 法院短信历史弹窗：分页浏览 + 按状态组筛选。覆盖：
 * - 打开时才请求（enabled: open）
 * - 三种列表态：加载中 / 错误（带重试）/ 空
 * - 行渲染：状态徽章、内容、时间、案件名、有无文书
 * - 切组重置到第 1 页
 * - 点某条回调 onPick(id)
 * - 分页：首末页禁用
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ listCourtSms: vi.fn() }))
vi.mock('../../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api')>()
  return { ...actual, listCourtSms: apiMock.listCourtSms }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { CourtSmsHistoryDialog } from './CourtSmsHistoryDialog'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function item(id: number, over: Record<string, unknown> = {}) {
  return {
    id,
    status: 'completed',
    content: `短信内容 ${id}`,
    received_at: '2026-10-20T10:00:00',
    case_name: null,
    has_documents: false,
    ...over,
  }
}

function renderDialog(props: Partial<Parameters<typeof CourtSmsHistoryDialog>[0]> = {}) {
  const onOpenChange = vi.fn()
  const onPick = vi.fn()
  const utils = render(
    wrap(<CourtSmsHistoryDialog open onOpenChange={onOpenChange} onPick={onPick} {...props} />),
  )
  return { ...utils, onOpenChange, onPick }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listCourtSms.mockResolvedValue({ items: [item(1)], count: 1 })
})

describe('CourtSmsHistoryDialog：请求时机', () => {
  it('open=false 时不请求', () => {
    const { unmount } = renderDialog({ open: false })
    expect(apiMock.listCourtSms).not.toHaveBeenCalled()
    unmount()
  })

  it('open=true 时按默认组 needs_action 与第 1 页请求', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(apiMock.listCourtSms).toHaveBeenCalledWith('needs_action', 1))
    unmount()
  })
})

describe('CourtSmsHistoryDialog：列表三态', () => {
  it('加载中显示提示', () => {
    apiMock.listCourtSms.mockReturnValue(new Promise(() => {}))
    const { unmount } = renderDialog()
    expect(screen.getByText('正在加载…')).toBeTruthy()
    unmount()
  })

  it('空列表显示空态', async () => {
    apiMock.listCourtSms.mockResolvedValue({ items: [], count: 0 })
    const { unmount } = renderDialog()
    await waitFor(() => expect(screen.getByText('这个筛选下没有记录')).toBeTruthy())
    unmount()
  })

  it('加载失败显示错误与重试', async () => {
    apiMock.listCourtSms.mockRejectedValue(new Error('网关超时'))
    const { unmount } = renderDialog()

    await waitFor(() => expect(screen.getByText(/网关超时/)).toBeTruthy())
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    unmount()
  })

  it('点重试重新请求', async () => {
    apiMock.listCourtSms.mockRejectedValueOnce(new Error('x')).mockResolvedValue({ items: [], count: 0 })
    const { unmount } = renderDialog()

    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    const before = apiMock.listCourtSms.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(apiMock.listCourtSms.mock.calls.length).toBeGreaterThan(before))
    unmount()
  })
})

describe('CourtSmsHistoryDialog：行渲染', () => {
  it('渲染内容、状态徽章与总数', async () => {
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())
    expect(document.body.textContent).toContain('1 条')
    // completed 映射为中文状态
    expect(document.body.textContent).toContain('已完成')
    container.remove()
  })

  it('未知状态回退显示原始值', async () => {
    apiMock.listCourtSms.mockResolvedValue({ items: [item(1, { status: 'weird_state' })], count: 1 })
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())
    expect(document.body.textContent).toContain('weird_state')
    container.remove()
  })

  it('有案件名与文书时显示对应片段', async () => {
    apiMock.listCourtSms.mockResolvedValue({
      items: [item(1, { case_name: '张三诉李四', has_documents: true })],
      count: 1,
    })
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('张三诉李四')).toBeTruthy())
    expect(document.body.textContent).toContain('·')
    container.remove()
  })

  it('点某行回调 onPick(id)', async () => {
    const { onPick, container } = renderDialog()
    const row = await waitFor(() => screen.getByText('短信内容 1').closest('button') as HTMLElement)
    fireEvent.click(row)
    expect(onPick).toHaveBeenCalledWith(1)
    container.remove()
  })
})

describe('CourtSmsHistoryDialog：切组与分页', () => {
  it('三个状态组按钮都在', async () => {
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())
    for (const label of ['需处理', '已完成', '全部']) {
      expect(within(document.body).getByRole('button', { name: label })).toBeTruthy()
    }
    container.remove()
  })

  it('切组用新组并重置到第 1 页', async () => {
    apiMock.listCourtSms.mockResolvedValue({ items: [item(1)], count: 100 })
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())

    // 先翻到第 2 页
    const nextBtn = within(document.body).getByRole('button', { name: /下一页/ })
    fireEvent.click(nextBtn)
    await waitFor(() => expect(apiMock.listCourtSms).toHaveBeenCalledWith('needs_action', 2))

    // 切组应回到第 1 页
    fireEvent.click(within(document.body).getByRole('button', { name: '全部' }))
    await waitFor(() => expect(apiMock.listCourtSms).toHaveBeenCalledWith('all', 1))
    container.remove()
  })

  it('多页时首页禁用「上一页」，末页禁用「下一页」', async () => {
    apiMock.listCourtSms.mockResolvedValue({ items: [item(1)], count: 100 })
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())

    const prev = within(document.body).getByRole('button', { name: /上一页/ }) as HTMLButtonElement
    expect(prev.disabled).toBe(true)
    container.remove()
  })

  it('总数不足一页时前后翻页按钮均禁用', async () => {
    apiMock.listCourtSms.mockResolvedValue({ items: [item(1)], count: 1 })
    const { container } = renderDialog()
    await waitFor(() => expect(screen.getByText('短信内容 1')).toBeTruthy())

    // 分页栏常驻，单页时两侧都禁用（而非隐藏）
    const prev = within(document.body).getByRole('button', { name: /上一页/ }) as HTMLButtonElement
    const next = within(document.body).getByRole('button', { name: /下一页/ }) as HTMLButtonElement
    expect(prev.disabled).toBe(true)
    expect(next.disabled).toBe(true)
    container.remove()
  })
})
