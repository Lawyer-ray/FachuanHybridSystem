// @vitest-environment jsdom
/**
 * InboxCard 测试（jsdom）。
 *
 * 三种状态必须互相区分（此前失败会被误读成「没有新消息」）：
 * - 加载中
 * - 加载失败（带重试）
 * - 空收件箱
 * 以及列表行渲染与点击打开。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listInbox: vi.fn(),
  parseReminder: vi.fn(),
  createReminder: vi.fn(),
  HOME_INBOX_KEY: ['home', 'inbox'],
}))

vi.mock('../api', () => ({ ...apiMock }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('@/features/document-recognition', () => ({
  preloadRecognizeDialog: vi.fn(),
  fileRejectReason: () => null,
  rowsFromParsed: (x: unknown) => x,
  RecognizeDialogLazy: () => null,
}))

import { InboxCard } from './SideCards'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function item(id: number, over: Record<string, unknown> = {}) {
  return {
    id,
    kind: 'sms',
    title: `消息 ${id}`,
    sourceLabel: '法院短信',
    who: '张三',
    at: '10:00',
    hot: false,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listInbox.mockResolvedValue([])
})

describe('InboxCard：三态', () => {
  it('加载中显示载入提示', () => {
    apiMock.listInbox.mockReturnValue(new Promise(() => {}))
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))
    expect(screen.getByText('正在载入…')).toBeTruthy()
    unmount()
  })

  it('空收件箱显示空态而非错误', async () => {
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))
    await waitFor(() => expect(screen.getByText('收件箱是空的')).toBeTruthy())
    expect(screen.queryByRole('button', { name: '重试' })).toBeNull()
    unmount()
  })

  it('加载失败显示错误文案与重试按钮，且不显示空态', async () => {
    apiMock.listInbox.mockRejectedValue(new Error('网关异常'))
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByText('网关异常')).toBeTruthy())
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    expect(screen.queryByText('收件箱是空的')).toBeNull()
    unmount()
  })

  it('点重试重新请求', async () => {
    apiMock.listInbox.mockRejectedValueOnce(new Error('异常')).mockResolvedValue([])
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByRole('button', { name: '重试' })).toBeTruthy())
    const before = apiMock.listInbox.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(apiMock.listInbox.mock.calls.length).toBeGreaterThan(before))
    unmount()
  })
})

describe('InboxCard：列表', () => {
  it('渲染标题、来源与人名', async () => {
    apiMock.listInbox.mockResolvedValue([item(1)])
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByText('消息 1')).toBeTruthy())
    expect(screen.getByText(/法院短信 · 张三/)).toBeTruthy()
    unmount()
  })

  it('计数丸显示条数', async () => {
    apiMock.listInbox.mockResolvedValue([item(1), item(2)])
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByText('2 条')).toBeTruthy())
    unmount()
  })

  it('点某行回调 onOpen 并带原始条目', async () => {
    const onOpen = vi.fn()
    const row = item(7)
    apiMock.listInbox.mockResolvedValue([row])
    const { unmount } = render(wrap(<InboxCard onOpen={onOpen} />))

    const btn = await waitFor(() => screen.getByText('消息 7').closest('button') as HTMLElement)
    fireEvent.click(btn)
    expect(onOpen).toHaveBeenCalledWith(row)
    unmount()
  })

  it('hot 条目带红色强调（与普通条目区分）', async () => {
    apiMock.listInbox.mockResolvedValue([item(1, { hot: true }), item(2, { hot: false })])
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByText('消息 1')).toBeTruthy())
    const hotIcon = screen.getByText('消息 1').closest('button')!.querySelector('div')
    expect(hotIcon!.className).toContain('status-red')
    unmount()
  })

  it('错误态不显示计数丸', async () => {
    apiMock.listInbox.mockRejectedValue(new Error('失败'))
    const { unmount } = render(wrap(<InboxCard onOpen={vi.fn()} />))

    await waitFor(() => expect(screen.getByText('失败')).toBeTruthy())
    expect(screen.queryByText(/条$/)).toBeNull()
    unmount()
  })
})
