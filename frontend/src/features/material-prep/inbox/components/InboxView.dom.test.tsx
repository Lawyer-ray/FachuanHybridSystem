// @vitest-environment jsdom
/**
 * 收件箱页 DOM 测试（jsdom）。
 *
 * 锁定三条最容易退化的用户路径：
 * 1. 列表按来源档位过滤 → 点档位后重新取数（参数对）；
 * 2. 点开一行 → 抽屉出现、并标记已读；
 * 3. 有附件的消息在抽屉里「转材料包」→ 跳材料预处理详情
 *    （这就是本次「点击后直接进入材料预处理」的闭环）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listInbox: vi.fn(),
  getInboxMessage: vi.fn(),
  setReadState: vi.fn(),
  convertToPack: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listInbox: apiMock.listInbox,
    getInboxMessage: apiMock.getInboxMessage,
    setReadState: apiMock.setReadState,
    convertToPack: apiMock.convertToPack,
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

// 下载票据与下载触发都是跨模块副作用（换票要发请求、downloadUrl 要操作 DOM），
// 在这里打桩以断言「确实换票了」——这正是曾经漏掉、导致 401 的那一步。
const dlMock = vi.hoisted(() => ({
  withDownloadTicket: vi.fn(async (u: string) => `${u}?ticket=TICKET123`),
  downloadUrl: vi.fn(),
}))
vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: dlMock.withDownloadTicket }))
vi.mock('@/lib/download', () => ({ downloadUrl: dlMock.downloadUrl }))

import { InboxView } from './InboxView'
import type { InboxRow } from '../types'

function row(over: Partial<InboxRow> & { id: number }): InboxRow {
  const now = new Date()
  return {
    source_name: '一张网收件箱',
    source_type: 'court_inbox',
    subject: '（20XX）粤0606执保XXXX号 - 告知书',
    sender: '某某人民法院',
    recipient: '',
    received_at: now.toISOString(),
    has_attachments: true,
    attachment_count: 2,
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: now.toISOString(),
    status: 'todo',
    segs: 0,
    named: 0,
    pages: 0,
    mats: 0,
    types: [],
    compose: '',
    is_read: false,
    upload_link_title: '',
    upload_contract_name: '',
    ...over,
  }
}

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/inbox']}>
        <Routes>
          <Route path="/inbox" element={node} />
          <Route path="/material-prep/:id" element={<div>材料预处理页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  dlMock.withDownloadTicket.mockClear()
  dlMock.withDownloadTicket.mockImplementation(async (u: string) => `${u}?ticket=TICKET123`)
  dlMock.downloadUrl.mockClear()
  apiMock.listInbox.mockReset()
  apiMock.getInboxMessage.mockReset()
  apiMock.setReadState.mockReset().mockResolvedValue({ ok: true, message_id: 1, is_read: true, read_at: '' })
  apiMock.convertToPack.mockReset().mockResolvedValue({ ok: true, message_id: 1, pack_id: 99 })
  apiMock.getInboxMessage.mockResolvedValue({
    id: 1,
    subject: '（20XX）粤0606执保XXXX号 - 告知书',
    body_text: '请于本通知送达后三日内提交材料。',
    body_html: '',
    attachments: [
      { filename: '裁定书.pdf', original_filename: '裁定书.pdf', size: 100, content_type: 'application/pdf', part_index: 0 },
    ],
  })
})

describe('InboxView', () => {
  it('渲染消息行（页面标题与阶段页签由 DeskPage 提供，不归本视图）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxView />)
    expect(await screen.findByText(/执保XXXX号/)).toBeTruthy()
    // 来源筛选条在（缩略确认这是列表本体而不是空壳）
    expect(screen.getByRole('button', { name: '邮箱' })).toBeTruthy()
  })

  it('切换来源档位会用对应 source_type 重新取数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxView />)
    await screen.findByText(/执保XXXX号/)
    fireEvent.click(screen.getByRole('button', { name: '邮箱' }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'imap' }))
    })
  })

  it('点开一行 → 抽屉出现并标记已读', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
    // 未读消息点开即标已读
    await waitFor(() => {
      expect(apiMock.setReadState).toHaveBeenCalledWith(1, true)
    })
  })

  it('已读的消息点开不重复发标记请求', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, is_read: true })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(apiMock.setReadState).not.toHaveBeenCalled()
  })

  it('抽屉内转材料包 → 跳材料预处理详情（闭环）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true, converted_message_id: null })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    const btn = await screen.findByRole('button', { name: /转材料包并打开/ })
    fireEvent.click(btn)
    await waitFor(() => {
      expect(apiMock.convertToPack).toHaveBeenCalledWith(1)
    })
    // 跳转后落到材料预处理路由
    expect(await screen.findByText('材料预处理页')).toBeTruthy()
  })

  // 回归：附件预览/下载曾用裸 <a href> 打开后端端点，浏览器带不上 JWT、
  // 后端又刻意不收 ?token=，导致任何账号都是 401（「用自己的账号下载自己的
  // 一张网材料也失败」，与权限无关）。必须经一次性下载票据换 ?ticket=。
  it('预览附件：先换下载票据，再带 ticket 开新标签', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    fireEvent.click(await screen.findByRole('button', { name: '预览附件' }))

    await waitFor(() => expect(dlMock.withDownloadTicket).toHaveBeenCalled())
    // 换票的入参必须是 preview 端点，且不含任何 JWT
    const arg = dlMock.withDownloadTicket.mock.calls[0]?.[0] as string
    expect(arg).toBe('/api/v1/inbox/messages/1/attachments/0/preview')
    await waitFor(() => expect(openSpy).toHaveBeenCalled())
    expect(String(openSpy.mock.calls[0]?.[0])).toContain('ticket=TICKET123')
    vi.unstubAllGlobals()
  })

  it('下载附件：先换下载票据，再以带 ticket 的 URL 触发下载', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    fireEvent.click(await screen.findByRole('button', { name: '下载附件' }))

    await waitFor(() => expect(dlMock.withDownloadTicket).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket.mock.calls[0]?.[0]).toBe(
      '/api/v1/inbox/messages/1/attachments/0/download',
    )
    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(String(dlMock.downloadUrl.mock.calls[0]?.[0])).toContain('ticket=TICKET123')
  })

  it('附件按钮不再渲染裸 <a href> 指向受保护端点（否则必然 401）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('button', { name: '预览附件' })
    const links = Array.from(document.querySelectorAll('a[href*="/attachments/"]'))
    expect(links).toHaveLength(0)
  })

  it('无附件的通知类消息不给转材料包按钮，并说明原因', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: false, attachment_count: 0 })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(screen.queryByRole('button', { name: /转材料包/ })).toBeNull()
    expect(screen.getByText(/没有附件，无可拆分材料/)).toBeTruthy()
  })

  it('已转过材料包的消息直接给「打开已转的材料包」', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, converted_message_id: 42 })])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('button', { name: /打开已转的材料包/ })).toBeTruthy()
  })

  it('材料包来源给「打开材料预处理」', async () => {
    apiMock.listInbox.mockResolvedValue([
      row({ id: 5, source_type: 'manual_upload', source_name: '前端材料预处理上传', subject: '手动上传材料' }),
    ])
    wrap(<InboxView />)
    fireEvent.click(await screen.findByText('手动上传材料'))
    expect(await screen.findByRole('button', { name: /打开材料预处理/ })).toBeTruthy()
  })

  it('未读筛选开关会用 unreadOnly 重新取数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxView />)
    await screen.findByText(/执保XXXX号/)
    fireEvent.click(screen.getByRole('button', { name: /未读/ }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ unreadOnly: true }))
    })
  })

  it('空列表按筛选条件给不同空态文案', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap(<InboxView />)
    expect(await screen.findByText('收件箱是空的')).toBeTruthy()
  })
})
